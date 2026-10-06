"""Verify the agent-token admin API end to end.

Runs inside the backend container. Mints via the API (not by direct DB write),
proves the minted token works, proves the plaintext is not recoverable from the
list, and proves revocation takes effect immediately.

Also asserts the security boundary that makes this feature safe: an agent's
bearer token must NOT be accepted on the admin routes.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.core.db import session_factory
from app.core.security import create_access_token
from app.models import DeviceToken, FamilyMember, Household
from app.services.agent_tokens import generate_token, hash_token

BACKEND = "http://localhost:8000"
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        if detail:
            print(f"        {detail}")
        failures.append(label)


async def main() -> int:
    async with session_factory() as session:
        household = (await session.execute(select(Household).limit(1))).scalars().first()
        parent = (
            await session.execute(
                select(FamilyMember).where(
                    FamilyMember.household_id == household.id,
                    FamilyMember.role == "parent",
                    FamilyMember.is_active.is_(True),
                ).limit(1)
            )
        ).scalars().first()

    if parent is None:
        print("SKIP  no active parent member to authenticate as")
        return 1

    # A cookie session for the human operator. No role claim: get_current_actor
    # derives the role and scopes from the member row, not from the token.
    cookie = create_access_token(
        member_id=str(parent.id),
        household_id=str(household.id),
    )
    human = {"access_token": cookie}

    minted_token = None
    minted_id = None
    agent_token = None
    agent_id = None

    try:
        with httpx.Client(timeout=20) as client:
            # --- the boundary: a bearer token must not open admin routes ---
            agent_token = generate_token()
            async with session_factory() as session:
                row = DeviceToken(
                    household_id=household.id,
                    member_id=None,
                    label="ADMINPROBE agent (auto-delete)",
                    token_hash=hash_token(agent_token),
                    scopes=["notes.read", "notes.write"],
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
                session.add(row)
                await session.commit()
                agent_id = row.id

            bearer = {"Authorization": f"Bearer {agent_token}"}
            for method, path in (
                ("get", "/api/admin/agent-tokens"),
                ("get", "/api/admin/agent-tokens/scopes"),
            ):
                response = getattr(client, method)(f"{BACKEND}{path}", headers=bearer)
                check(
                    f"agent bearer token rejected on {method.upper()} {path}",
                    response.status_code in (401, 403),
                    f"got {response.status_code} — an agent could manage its own tokens",
                )

            # --- unauthenticated must be rejected too ---
            anon = client.get(f"{BACKEND}/api/admin/agent-tokens")
            check("unauthenticated list rejected", anon.status_code == 401, f"got {anon.status_code}")

            # --- scopes catalog ---
            scopes = client.get(f"{BACKEND}/api/admin/agent-tokens/scopes", cookies=human)
            check("scope catalog served", scopes.status_code == 200, f"got {scopes.status_code}")
            catalog = scopes.json()
            check("catalog lists notes.write", "notes.write" in catalog, str(catalog))

            # --- mint ---
            created = client.post(
                f"{BACKEND}/api/admin/agent-tokens",
                cookies=human,
                json={"label": "MINT PROBE (auto-delete)", "scopes": ["notes.read", "notes.write"],
                      "expires_in_days": 1},
            )
            check("mint succeeds", created.status_code == 201, f"got {created.status_code}: {created.text[:160]}")
            if created.status_code != 201:
                return 1
            body = created.json()
            minted_token = body["token"]
            minted_id = body["id"]
            check("mint returns a usable-looking token", minted_token.startswith("fos_"), minted_token[:12])
            check("mint reports scopes", body["scopes"] == ["notes.read", "notes.write"], str(body["scopes"]))
            check("mint reports active", body["is_active"] is True)
            check("mint carries a warning", bool(body.get("warning")))

            # --- unknown scope refused ---
            bad = client.post(
                f"{BACKEND}/api/admin/agent-tokens",
                cookies=human,
                json={"label": "bad", "scopes": ["notes.read", "totally.made.up"]},
            )
            check("unknown scope refused", bad.status_code == 422, f"got {bad.status_code}")

            # --- blank label refused ---
            blank = client.post(
                f"{BACKEND}/api/admin/agent-tokens",
                cookies=human,
                json={"label": "   ", "scopes": ["notes.read"]},
            )
            check("blank label refused", blank.status_code == 422, f"got {blank.status_code}")

            # --- list never leaks the secret ---
            listed = client.get(f"{BACKEND}/api/admin/agent-tokens", cookies=human)
            check("list succeeds", listed.status_code == 200, f"got {listed.status_code}")
            rows = listed.json()
            check("minted token appears in the list", any(r["id"] == minted_id for r in rows))
            blob = listed.text
            check("list does not contain the plaintext token", minted_token not in blob)
            check("list does not expose token_hash", "token_hash" not in blob)
            check("list marks it active", any(r["id"] == minted_id and r["is_active"] for r in rows))

            # --- the minted token actually works on MCP ---
            mcp_headers = {
                "Authorization": f"Bearer {minted_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            init = client.post(
                f"{BACKEND}/mcp/", headers=mcp_headers, follow_redirects=True,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "mint-probe", "version": "1"}}},
            )
            check("minted token authenticates on MCP", init.status_code == 200, f"got {init.status_code}")

            # --- revoke ---
            revoked = client.delete(f"{BACKEND}/api/admin/agent-tokens/{minted_id}", cookies=human)
            check("revoke succeeds", revoked.status_code == 200, f"got {revoked.status_code}")

            after = client.get(f"{BACKEND}/api/admin/agent-tokens", cookies=human).json()
            target = next((r for r in after if r["id"] == minted_id), None)
            check("revoked token still listed (audit trail)", target is not None)
            check("revoked token marked inactive", target is not None and target["is_active"] is False)
            check("revoked token carries revoked_at", target is not None and target["revoked_at"] is not None)

            # --- revoked token must stop working immediately ---
            dead = client.post(
                f"{BACKEND}/mcp/", headers=mcp_headers, follow_redirects=True,
                json={"jsonrpc": "2.0", "id": 2, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "mint-probe", "version": "1"}}},
            )
            check("revoked token refused on MCP", dead.status_code in (401, 403), f"got {dead.status_code}")

            # --- revoking twice is harmless ---
            again = client.delete(f"{BACKEND}/api/admin/agent-tokens/{minted_id}", cookies=human)
            check("revoking twice is idempotent", again.status_code == 200, f"got {again.status_code}")

            # --- unknown id 404 ---
            missing = client.delete(
                f"{BACKEND}/api/admin/agent-tokens/00000000-0000-0000-0000-000000000000", cookies=human
            )
            check("unknown token id 404s", missing.status_code == 404, f"got {missing.status_code}")
    finally:
        async with session_factory() as session:
            for token_id in (minted_id, agent_id):
                if token_id is None:
                    continue
                row = await session.get(DeviceToken, token_id)
                if row is not None:
                    await session.delete(row)
            await session.commit()
            print("cleaned up probe tokens")

    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


raise SystemExit(asyncio.run(main()))
