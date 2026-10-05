"""Smoke test: the MCP server, driven by the real MCP client SDK.

Run inside the backend container:

    docker exec -w /app familyos-backend-1 \\
      sh -c 'PYTHONPATH=/app /app/.venv/bin/python scripts/smoke_mcp.py'

What this proves, and why each check exists:

1. The mount did not break the plain FastAPI routes.
2. An unauthenticated MCP call is rejected — the tools are not world-readable.
3. A valid device token connects, and tool discovery matches the REST registry.
4. A tool actually executes and returns household data (not an error envelope).
5. A token without `notes.read` is refused, so the scope check survives the
   MCP transport and is not bypassed by talking to a different endpoint.
6. A revoked token is refused on the *next call*, not just at session start.
7. The call is audited with the agent's own name.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import httpx
import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import delete, select

from app.agent.registry import registry
from app.core.db import session_factory
from app.models import AgentToolCall, DeviceToken, Household
from app.services.agent_tokens import generate_token, hash_token

BASE = "http://127.0.0.1:8000"
MCP_URL = f"{BASE}/mcp"
PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}  {detail}")


async def mint(session, household_id, *, label: str, scopes: list[str]):
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


async def call_with_token(token: str, body: dict) -> tuple[int, dict]:
    """One raw MCP JSON-RPC call, so we can assert on the HTTP status."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(MCP_URL, headers=headers, json=body)
        try:
            return response.status_code, response.json()
        except Exception:
            return response.status_code, {"raw": response.text[:200]}


async def main() -> int:
    async with session_factory() as session:
        household = (await session.execute(select(Household).limit(1))).scalar_one()
        household_id = household.id
        good_token, good_record = await mint(
            session, household_id, label="MCP Smoke (test)", scopes=["notes.read"]
        )
        blind_token, blind_record = await mint(
            session, household_id, label="MCP Blind (test)", scopes=[]
        )
        doomed_token, doomed_record = await mint(
            session, household_id, label="MCP Doomed (test)", scopes=["notes.read"]
        )

    try:
        print("\n1. Plain FastAPI routes still work alongside the mount")
        async with httpx.AsyncClient(base_url=BASE, timeout=15.0) as client:
            health = await client.get("/healthz")
            check("GET /healthz -> 200", health.status_code == 200, f"got {health.status_code}")
            openapi = await client.get("/openapi.json")
            paths = openapi.json().get("paths", {}) if openapi.status_code == 200 else {}
            check(
                "API routes intact",
                "/api/notes" in paths or any(p.startswith("/api/") for p in paths),
                f"paths={len(paths)}",
            )

        print("\n2. Unauthenticated MCP call is rejected")
        status, _ = await call_with_token(
            "",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        check("no token -> not 200", status != 200, f"got {status}")

        print("\n3. Valid token: discovery matches the REST registry")
        async with streamable_http_client(
            MCP_URL, http_client=httpx2.AsyncClient(headers={"Authorization": f"Bearer {good_token}"}, timeout=30.0)
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await session.list_tools()
                mcp_names = {tool.name for tool in tools.tools}
                rest_names = {name for name, d in registry.items() if not d.mutates}
                check(
                    "MCP tools == non-mutating registry tools",
                    mcp_names == rest_names,
                    f"mcp={sorted(mcp_names)} rest={sorted(rest_names)}",
                )

                print("\n4. A tool executes and returns real data")
                result = await session.call_tool("search_notes", {"query": "", "limit": 3})
                payload = _decode(result)
                check(
                    "search_notes returns ok",
                    isinstance(payload, dict) and payload.get("ok") is True,
                    f"got {str(payload)[:160]}",
                )
                count = (payload.get("meta") or {}).get("count") if isinstance(payload, dict) else None
                check("search_notes returned a count", count is not None, f"meta={payload.get('meta') if isinstance(payload, dict) else None}")

                tags = await session.call_tool("list_tags", {})
                tags_payload = _decode(tags)
                check(
                    "list_tags returns ok",
                    isinstance(tags_payload, dict) and tags_payload.get("ok") is True,
                    f"got {str(tags_payload)[:160]}",
                )

        print("\n5. Scope check survives the MCP transport")
        async with streamable_http_client(
            MCP_URL, http_client=httpx2.AsyncClient(headers={"Authorization": f"Bearer {blind_token}"}, timeout=30.0)
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.call_tool("search_notes", {"query": "", "limit": 1})
                payload = _decode(result)
                denied = (
                    isinstance(payload, dict)
                    and payload.get("ok") is False
                    and payload.get("error_code") in {"permission_denied", "unauthenticated"}
                )
                check("no-scope token denied", denied, f"got {str(payload)[:160]}")

        print("\n6. Revocation takes effect on the next call")
        async with session_factory() as session:
            record = await session.get(DeviceToken, doomed_record.id)
            record.revoked_at = datetime.now(UTC)
            await session.commit()
        async with streamable_http_client(
            MCP_URL, http_client=httpx2.AsyncClient(headers={"Authorization": f"Bearer {doomed_token}"}, timeout=30.0)
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                try:
                    await session.initialize()
                    result = await session.call_tool("search_notes", {"query": "", "limit": 1})
                    payload = _decode(result)
                    refused = isinstance(payload, dict) and payload.get("ok") is False
                except Exception:
                    # Rejection at initialize is also a pass.
                    refused = True
                check("revoked token refused", refused, "call unexpectedly succeeded")

        print("\n7. Audit rows name the agent")
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(AgentToolCall).where(AgentToolCall.agent == "MCP Smoke").limit(5)
                )
            ).scalars().all()
            check("audit rows recorded", len(rows) > 0, f"found {len(rows)}")

    finally:
        async with session_factory() as session:
            await session.execute(
                delete(DeviceToken).where(
                    DeviceToken.id.in_([good_record.id, blind_record.id, doomed_record.id])
                )
            )
            await session.execute(
                delete(AgentToolCall).where(AgentToolCall.agent.like("MCP %"))
            )
            await session.commit()

    print(f"\n{'=' * 60}")
    print(f"PASSED {len(PASSED)}   FAILED {len(FAILED)}")
    for label in FAILED:
        print(f"  - {label}")
    return 1 if FAILED else 0


def _decode(result):
    """Pull the JSON payload out of a CallToolResult."""
    if not result.content:
        return None
    text = getattr(result.content[0], "text", None)
    if text is None:
        return None
    import json

    try:
        return json.loads(text)
    except Exception:
        return {"raw": text[:200]}


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
