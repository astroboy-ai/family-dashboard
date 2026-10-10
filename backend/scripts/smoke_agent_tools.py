"""Smoke test: the internal agent API, end to end over real HTTP.

Run inside the backend container (see the remote-docker-deploy skill,
references/in-container-smoke-tests.md):

    docker exec -w /app familyos-backend-1 \\
      sh -c 'PYTHONPATH=/app /app/.venv/bin/python scripts/smoke_agent_tools.py'

What this proves, and why each check exists:

1. An unauthenticated call is rejected — the endpoint is not accidentally open.
2. An unknown token is rejected, with the same shape as a revoked one.
3. A valid token lists the tools.
4. Every registered read-only tool can actually be invoked.
5. A token WITHOUT the required scope is denied, while one WITH it succeeds —
   the permission check is live, not decorative.
6. The caller cannot name its own identity: the old body fields are ignored.
7. A revoked token stops working immediately.
8. Each call leaves an audit row naming the calling agent.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select

from app.core.db import session_factory
from app.models import AgentToolCall, DeviceToken, Household, Note
from app.services.agent_tokens import generate_token, hash_token

BASE = "http://127.0.0.1:8000"
PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}  {detail}")


async def mint(session, household_id, *, label: str, scopes: list[str]) -> tuple[str, DeviceToken]:
    token = generate_token()
    record = DeviceToken(
        household_id=household_id,
        member_id=None,
        label=label,
        token_hash=hash_token(token),
        scopes=scopes,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return token, record


async def main() -> int:
    async with session_factory() as session:
        household = (await session.execute(select(Household).limit(1))).scalar_one()
        household_id = household.id

        # A note the agent should be able to see (family visibility).
        note = (
            await session.execute(
                select(Note).where(
                    Note.household_id == household_id,
                    Note.visibility == "family",
                    Note.deleted_at.is_(None),
                ).limit(1)
            )
        ).scalars().first()
        note_id = str(note.id) if note else None

        full_token, full_record = await mint(
            session, household_id, label="Smoke Full (test)", scopes=["notes.read"]
        )
        blind_token, blind_record = await mint(
            session, household_id, label="Smoke Blind (test)", scopes=[]
        )
        doomed_token, doomed_record = await mint(
            session, household_id, label="Smoke Revoked (test)", scopes=["notes.read"]
        )

    auth_full = {"Authorization": f"Bearer {full_token}"}
    auth_blind = {"Authorization": f"Bearer {blind_token}"}

    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
            print("\n1. Unauthenticated is rejected")
            response = await client.get("/internal/agent/tools")
            check("no token -> 401", response.status_code == 401, f"got {response.status_code}")

            print("\n2. Unknown token is rejected")
            response = await client.get(
                "/internal/agent/tools", headers={"Authorization": "Bearer not-a-real-token"}
            )
            check("bad token -> 401", response.status_code == 401, f"got {response.status_code}")

            print("\n3. Valid token lists tools")
            response = await client.get("/internal/agent/tools", headers=auth_full)
            check("tools -> 200", response.status_code == 200, f"got {response.status_code}")
            tools = response.json() if response.status_code == 200 else []
            names = {tool["name"] for tool in tools}
            expected = {
                "search_notes",
                "get_note",
                "get_blocks",
                "list_tags",
                "get_expiring_items",
            }
            check(
                "all 5 tools listed",
                expected.issubset(names),
                f"missing {expected - names}",
            )

            print("\n4. Every read-only tool is invocable")
            calls = [
                ("search_notes", {"query": "", "limit": 5}),
                ("list_tags", {}),
                ("get_expiring_items", {"days": 365}),
            ]
            if note_id:
                calls.append(("get_note", {"note_id": note_id, "include_blocks": False}))
                calls.append(("get_blocks", {"note_id": note_id}))
            for name, params in calls:
                response = await client.post(
                    f"/internal/agent/tools/{name}", headers=auth_full, json={"params": params}
                )
                body = response.json() if response.status_code == 200 else {}
                ok = response.status_code == 200 and body.get("ok") is True
                check(
                    f"{name} -> ok",
                    ok,
                    f"status={response.status_code} body={str(body)[:120]}",
                )

            print("\n5. Scope check is live")
            response = await client.post(
                "/internal/agent/tools/list_tags", headers=auth_blind, json={"params": {}}
            )
            body = response.json() if response.status_code == 200 else {}
            check(
                "no-scope token -> permission_denied",
                body.get("error_code") == "permission_denied",
                f"got {str(body)[:120]}",
            )

            print("\n6. Caller cannot name its own identity")
            response = await client.post(
                "/internal/agent/tools/list_tags",
                headers=auth_blind,
                json={
                    "params": {},
                    # Fields from the old design: must be ignored, not honoured.
                    "household_id": str(household_id),
                    "actor_member_id": "00000000-0000-0000-0000-000000000000",
                },
            )
            body = response.json() if response.status_code == 200 else {}
            check(
                "body identity fields ignored",
                body.get("error_code") == "permission_denied",
                f"got {str(body)[:120]}",
            )

            print("\n7. Revocation takes effect immediately")
            async with session_factory() as session:
                record = await session.get(DeviceToken, doomed_record.id)
                record.revoked_at = datetime.now(UTC)
                await session.commit()
            response = await client.post(
                "/internal/agent/tools/list_tags",
                headers={"Authorization": f"Bearer {doomed_token}"},
                json={"params": {}},
            )
            check(
                "revoked token -> 401",
                response.status_code == 401,
                f"got {response.status_code}",
            )

        print("\n8. Audit rows name the calling agent")
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(AgentToolCall)
                    .where(AgentToolCall.agent == "Smoke Full")
                    .limit(5)
                )
            ).scalars().all()
            check("audit rows recorded", len(rows) > 0, f"found {len(rows)}")
            check(
                "audit actor_member_id is null for service token",
                all(row.actor_member_id is None for row in rows),
                "expected null",
            )

    finally:
        # Clean up only what this test created.
        async with session_factory() as session:
            await session.execute(
                delete(DeviceToken).where(
                    DeviceToken.id.in_([full_record.id, blind_record.id, doomed_record.id])
                )
            )
            await session.execute(
                delete(AgentToolCall).where(AgentToolCall.agent.like("Smoke %"))
            )
            await session.commit()

    print(f"\n{'=' * 60}")
    print(f"PASSED {len(PASSED)}   FAILED {len(FAILED)}")
    if FAILED:
        for label in FAILED:
            print(f"  - {label}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
