"""Real end-to-end test of the refresh-token session (CR-004).

Runs inside the backend container against the live HTTP API and the real
database. Exercises the full lifecycle plus the failure modes that matter:

1. refresh rotates and yields a working access token;
2. the old refresh token is dead (no replay);
3. reusing a rotated token revokes the whole chain (theft response);
4. logout revokes and clears;
5. the relay upload path stores bytes, completes, and round-trips.

Cookies are tracked by hand (not via httpx's jar) because access_token and
refresh_token live on different paths and httpx raises on the ambiguity.
"""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.core.db import session_factory
from app.models import FamilyMember, MediaAsset, RefreshToken
from app.services.sessions import issue_session

BASE = "http://127.0.0.1:8000"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{' — ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def cookies_from(response: httpx.Response, **current: str) -> dict[str, str]:
    """Merge any Set-Cookie values from *response* into the running jar."""
    jar = dict(current)
    for value in response.headers.get_list("set-cookie"):
        name, _, rest = value.partition("=")
        jar[name.strip()] = rest.split(";")[0]
    return jar


def cookie_header(jar: dict[str, str]) -> dict[str, str]:
    return {"Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())}


async def main() -> None:
    async with session_factory() as session:
        member = (
            await session.execute(select(FamilyMember).where(FamilyMember.role == "parent").limit(1))
        ).scalar_one()
        mid = member.id
        issued = await issue_session(session=session, member=member, user_agent="smoke-test")
        first_token = issued.refresh_token
        assert first_token is not None  # a fresh issue always returns one

    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        jar = {"refresh_token": first_token}

        # --- 1. refresh rotates, access token works ------------------------
        r = await client.post("/api/auth/refresh", headers=cookie_header(jar))
        check("refresh returns 200", r.status_code == 200, f"got {r.status_code} {r.text[:120]}")
        jar = cookies_from(r, **jar)
        check("refresh returned an access token", "access_token" in jar)
        check("refresh rotated the refresh token", jar.get("refresh_token") != first_token)

        r = await client.get("/api/auth/me", headers=cookie_header(jar))
        check("access token works on /auth/me", r.status_code == 200, f"got {r.status_code}")

        # --- 2. a replay inside the grace window is a RACE, not theft ------
        # Two tabs, or a refresh response lost on a flaky mobile link, both look
        # like a replay in the database. Inside the grace window we hand back an
        # access token and keep the chain alive; the caller already holds the
        # successor refresh token so no new one is issued.
        r = await client.post(
            "/api/auth/refresh", headers={"Cookie": f"refresh_token={first_token}"}
        )
        check(
            "in-grace replay tolerated (race)",
            r.status_code == 200,
            f"got {r.status_code} {r.text[:120]}",
        )
        check(
            "in-grace replay does not re-issue a refresh cookie",
            "refresh_token" not in cookies_from(r),
        )

        r = await client.get("/api/auth/me", headers=cookie_header(jar))
        check(
            "successor token still valid after in-grace replay",
            r.status_code == 200,
            f"got {r.status_code}",
        )

        # --- 3. a replay OUTSIDE the grace window is theft -----------------
        # Backdate the rotation so the replay looks like it happened later.
        async with session_factory() as session:
            stale = (
                await session.execute(
                    select(RefreshToken).where(
                        RefreshToken.token_hash
                        == hashlib.sha256(first_token.encode("utf-8")).hexdigest()
                    )
                )
            ).scalar_one()
            stale.rotated_at = datetime.now(UTC) - timedelta(seconds=120)
            await session.commit()

        r = await client.post(
            "/api/auth/refresh", headers={"Cookie": f"refresh_token={first_token}"}
        )
        check("late replay rejected", r.status_code == 401, f"got {r.status_code}")

        r = await client.post("/api/auth/refresh", headers=cookie_header(jar))
        check("chain revoked after late replay", r.status_code == 401, f"got {r.status_code}")

        async with session_factory() as session:
            chain = (
                await session.execute(
                    select(RefreshToken).where(
                        RefreshToken.member_id == mid,
                        RefreshToken.family_id == issued.family_id,
                    )
                )
            ).scalars().all()
            check("reuse recorded for audit", any(row.reuse_detected_at for row in chain))
            live = [row for row in chain if row.revoked_at is None and row.rotated_at is None]
            check("whole chain revoked", len(live) == 0, f"{len(live)} still live in chain")

        # --- 4. a fresh session works, then logout revokes it --------------
        async with session_factory() as session:
            member = (await session.execute(select(FamilyMember).where(FamilyMember.id == mid))).scalar_one()
            fresh = await issue_session(session=session, member=member)
            fresh_token = fresh.refresh_token
            assert fresh_token is not None

        # --- 3b. an aged-out ACCESS token alone must not kill the session --
        # This is the CR-02 regression: the access token (15 min) expires while
        # the refresh token (30 days) is still perfectly good. Presenting a
        # *stale* access cookie with a *valid* refresh cookie must be
        # recoverable — that is exactly what the frontend does on every page
        # load. We assert the backend half here (the frontend retry is covered
        # by the browser check).
        jar_stale = {"refresh_token": fresh_token, "access_token": "expired.jwt.value"}
        r = await client.get("/api/auth/me", headers=cookie_header(jar_stale))
        check(
            "stale access token is a 401 (triggers frontend refresh)",
            r.status_code == 401,
            f"got {r.status_code}",
        )

        r = await client.post("/api/auth/refresh", headers=cookie_header(jar_stale))
        check(
            "valid refresh token recovers the session",
            r.status_code == 200,
            f"got {r.status_code} {r.text[:120]}",
        )
        jar_stale = cookies_from(r, **jar_stale)

        r = await client.get("/api/auth/me", headers=cookie_header(jar_stale))
        check(
            "/auth/me succeeds after refresh (CR-02 fix)",
            r.status_code == 200,
            f"got {r.status_code}",
        )

        async with session_factory() as session:
            member = (await session.execute(select(FamilyMember).where(FamilyMember.id == mid))).scalar_one()
            fresh = await issue_session(session=session, member=member)
            fresh_token = fresh.refresh_token
            assert fresh_token is not None

        jar2 = {"refresh_token": fresh_token}
        r = await client.post("/api/auth/refresh", headers=cookie_header(jar2))
        check("fresh session refreshes", r.status_code == 200, f"got {r.status_code}")
        jar2 = cookies_from(r, **jar2)

        r = await client.post("/api/auth/logout", headers=cookie_header(jar2))
        check("logout returns 204", r.status_code == 204, f"got {r.status_code}")

        r = await client.post("/api/auth/refresh", headers=cookie_header(jar2))
        check("refresh after logout rejected", r.status_code == 401, f"got {r.status_code}")

        # --- 5. relay upload ----------------------------------------------
        async with session_factory() as session:
            member = (await session.execute(select(FamilyMember).where(FamilyMember.id == mid))).scalar_one()
            s3 = await issue_session(session=session, member=member)

        jar3 = {"refresh_token": s3.refresh_token}
        r = await client.post("/api/auth/refresh", headers=cookie_header(jar3))
        jar3 = cookies_from(r, **jar3)

        r = await client.post(
            "/api/media/presign",
            json={
                "filename": "relay.png",
                "mime": "image/png",
                "size": len(PNG),
                "sha256": hashlib.sha256(PNG).hexdigest(),
            },
            headers=cookie_header(jar3),
        )
        check("presign ok", r.status_code == 201, f"got {r.status_code} {r.text[:120]}")
        asset_id = r.json()["asset_id"]

        r = await client.put(
            f"/api/media/{asset_id}/content",
            content=PNG,
            headers={**cookie_header(jar3), "Content-Type": "image/png"},
        )
        check("relay upload accepted", r.status_code == 200, f"got {r.status_code} {r.text[:160]}")

        r = await client.get(f"/api/media/{asset_id}/download", headers=cookie_header(jar3))
        check(
            "relay upload round-trips",
            r.status_code == 200 and r.content == PNG,
            f"got {r.status_code}, {len(r.content)} bytes",
        )

        # A second PUT to a completed asset must be a no-op, not an overwrite.
        r = await client.put(
            f"/api/media/{asset_id}/content",
            content=PNG,
            headers={**cookie_header(jar3), "Content-Type": "image/png"},
        )
        check(
            "re-upload to a complete asset is idempotent",
            r.status_code == 200 and r.json().get("already_complete") is True,
            f"got {r.status_code} {r.text[:120]}",
        )

        # Size mismatch is only checked while the asset is still "uploading".
        r = await client.post(
            "/api/media/presign",
            json={
                "filename": "mismatch.png",
                "mime": "image/png",
                "size": len(PNG),
                "sha256": hashlib.sha256(PNG + b"other").hexdigest(),
            },
            headers=cookie_header(jar3),
        )
        bad_id = r.json()["asset_id"]
        r = await client.put(
            f"/api/media/{bad_id}/content",
            content=PNG + b"x",
            headers={**cookie_header(jar3), "Content-Type": "image/png"},
        )
        check("size mismatch rejected", r.status_code == 422, f"got {r.status_code} {r.text[:120]}")

        async with session_factory() as session:
            for stale_id in (asset_id, bad_id):
                asset = await session.get(MediaAsset, stale_id)
                if asset:
                    await session.delete(asset)
            await session.commit()

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        raise SystemExit(1)
    print("ALL SESSION + RELAY TESTS PASSED")


asyncio.run(main())
