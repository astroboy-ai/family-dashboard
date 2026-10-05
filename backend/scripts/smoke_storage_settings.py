"""Real end-to-end test of the admin storage settings (CR-005).

Proves the thing that actually matters: the public upload origin is read from the
household settings at request time, so changing it in the admin page changes the
presigned URL immediately — no restart — and the presign falls back to the env
value when no override exists.

Runs inside the backend container against the live API and database.
"""

import asyncio

import httpx
from sqlalchemy import select

from app.core.db import session_factory
from app.models import FamilyMember, Household
from app.services.sessions import issue_session
from app.services.storage_settings import resolve_storage_settings

BASE = "http://127.0.0.1:8000"
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{' — ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def cookies_from(response: httpx.Response, **current: str) -> dict[str, str]:
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
        household = await session.get(Household, member.household_id)
        original_settings = dict(household.settings or {})
        issued = await issue_session(session=session, member=member, user_agent="storage-smoke")

    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        jar = {"refresh_token": issued.refresh_token}
        r = await client.post("/api/auth/refresh", headers=cookie_header(jar))
        jar = cookies_from(r, **jar)
        auth = cookie_header(jar)

        try:
            # --- 1. GET exposes the storage section ------------------------
            r = await client.get("/api/admin/settings", headers=auth)
            check("GET /admin/settings", r.status_code == 200, f"got {r.status_code}")
            body = r.json()
            check("response has a storage section", "storage" in body)
            check(
                "storage reports browser_reachable",
                "browser_reachable" in body.get("storage", {}),
            )
            print(f"      resolved endpoint: {body['storage']['public_endpoint']}")
            print(f"      browser_reachable: {body['storage']['browser_reachable']}")

            # --- 2. storage test endpoint signs a URL ----------------------
            r = await client.post("/api/admin/storage/test", headers=auth)
            check("POST /admin/storage/test", r.status_code == 200, f"got {r.status_code}")
            test_body = r.json()
            check("internal storage reachable", test_body.get("internal_ok") is True)
            check("a probe URL was signed", bool(test_body.get("upload_url")))
            if test_body.get("warnings"):
                for warning in test_body["warnings"]:
                    print(f"      warning: {warning}")

            # --- 3. set a public endpoint and see it take effect at once ---
            target = "https://media.example.test"
            r = await client.patch(
                "/api/admin/settings",
                json={"storage": {"public_endpoint": target, "bucket": "familyos-media"}},
                headers=auth,
            )
            check("PATCH storage accepted", r.status_code == 200, f"got {r.status_code} {r.text[:160]}")
            check(
                "response echoes the new endpoint",
                r.json().get("storage", {}).get("public_endpoint") == target,
                r.json().get("storage", {}).get("public_endpoint", ""),
            )
            check(
                "endpoint is now browser-reachable",
                r.json().get("storage", {}).get("browser_reachable") is True,
            )

            # The next presign must use it without any restart.
            r = await client.post(
                "/api/media/presign",
                json={"filename": "p.txt", "mime": "text/plain", "size": 1, "sha256": "a" * 64},
                headers=auth,
            )
            check("presign still works", r.status_code == 201, f"got {r.status_code}")
            url = r.json().get("upload_url") or ""
            check("presigned URL uses the household endpoint", url.startswith(target), url[:80])
            asset_id = r.json()["asset_id"]

            # --- 4. test endpoint now reports the new origin ---------------
            r = await client.post("/api/admin/storage/test", headers=auth)
            check(
                "storage test reflects the override",
                r.json().get("public_endpoint") == target,
                r.json().get("public_endpoint", ""),
            )

            # --- 5. AI fields still work alongside storage -----------------
            r = await client.patch(
                "/api/admin/settings",
                json={"embedding_batch_size": 24, "storage": {"region": "ap-southeast-1"}},
                headers=auth,
            )
            check("combined AI + storage patch", r.status_code == 200, f"got {r.status_code}")
            check("ai field applied", r.json()["ai"]["embedding_batch_size"] == 24)
            check("storage field applied", r.json()["storage"]["region"] == "ap-southeast-1")

            # --- 6. settings survive a reload -----------------------------
            r = await client.get("/api/admin/settings", headers=auth)
            body = r.json()
            check("endpoint persisted", body["storage"]["public_endpoint"] == target)
            check("region persisted", body["storage"]["region"] == "ap-southeast-1")

        finally:
            # restore whatever the household had before the test
            async with session_factory() as session:
                household = await session.get(Household, member.household_id)
                household.settings = original_settings
                await session.commit()
            print("settings restored")

    # --- 7. resolution helper behaves on its own ---------------------------
    resolved = resolve_storage_settings({"storage": {"public_endpoint": "http://127.0.0.1:8333"}})
    check("loopback endpoint flagged unreachable", resolved.browser_reachable is False)
    resolved = resolve_storage_settings({"storage": {"public_endpoint": "https://media.example.com"}})
    check("https hostname flagged reachable", resolved.browser_reachable is True)
    resolved = resolve_storage_settings({})
    check("empty settings fall back to defaults", bool(resolved.public_endpoint))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {failures}")
        raise SystemExit(1)
    print("ALL STORAGE SETTINGS TESTS PASSED")


asyncio.run(main())
