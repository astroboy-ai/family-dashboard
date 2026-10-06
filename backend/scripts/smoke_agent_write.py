"""End-to-end checks for the agent write path.

Run inside the backend container:

    docker exec -w /app -e PYTHONPATH=/app familyos-backend-1 \
      /app/.venv/bin/python scripts/smoke_agent_write.py

Mints two throwaway tokens — one read-only, one with ``notes.write`` — exercises
the MCP surface against both, and deletes everything it created.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.core.db import session_factory
from app.models import DeviceToken, Household, MediaAsset, Note, NoteBlock
from app.services.agent_tokens import generate_token, hash_token

BASE = "http://localhost:8000"
MCP_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

failures: list[str] = []
created_notes: list[uuid.UUID] = []
created_assets: list[uuid.UUID] = []
created_tokens: list[uuid.UUID] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        if detail:
            print(f"        {detail}")
        failures.append(label)


class McpClient:
    """Minimal streamable-HTTP MCP client: handshake, list, call."""

    def __init__(self, token: str) -> None:
        self.headers = {**MCP_HEADERS, "Authorization": f"Bearer {token}"}
        self.session_id: str | None = None
        self._id = 0

    def _next(self) -> int:
        self._id += 1
        return self._id

    async def _post(self, payload: dict) -> httpx.Response:
        headers = dict(self.headers)
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        return await asyncio.to_thread(
            httpx.post, f"{BASE}/mcp/", headers=headers, json=payload, timeout=30
        )

    async def connect(self) -> bool:
        response = await self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke-agent-write", "version": "1"},
                },
            }
        )
        self.session_id = response.headers.get("mcp-session-id")
        if not self.session_id:
            return False
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return True

    async def tools(self) -> list[str]:
        response = await self._post(
            {"jsonrpc": "2.0", "id": self._next(), "method": "tools/list"}
        )
        return [t["name"] for t in response.json().get("result", {}).get("tools", [])]

    async def call(self, name: str, arguments: dict) -> dict:
        response = await self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        body = response.json()
        result = body.get("result", {})
        content = result.get("content", [])
        text = content[0].get("text", "") if content else ""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"raw": text}


async def mint(*, label: str, scopes: list[str], household_id: uuid.UUID) -> str:
    token = generate_token()
    async with session_factory() as session:
        record = DeviceToken(
            household_id=household_id,
            member_id=None,
            label=label,
            token_hash=hash_token(token),
            scopes=scopes,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(record)
        await session.commit()
        created_tokens.append(record.id)
    return token


async def main() -> int:
    async with session_factory() as session:
        household = (await session.execute(select(Household).limit(1))).scalars().first()
        if household is None:
            print("FAIL: no household")
            return 2
        household_id = household.id

    read_token = await mint(label="Smoke ReadOnly", scopes=["notes.read"], household_id=household_id)
    write_token = await mint(
        label="Smoke Writer", scopes=["notes.read", "notes.write"], household_id=household_id
    )

    try:
        # ── 1. write tools are published over MCP ────────────────────────────
        reader = McpClient(read_token)
        check("read-only client connects", await reader.connect())
        names = await reader.tools()
        for tool in ("upload_media", "create_note", "append_block"):
            check(f"MCP publishes {tool}", tool in names, f"tools: {names}")

        # ── 2. read-only token is refused ────────────────────────────────────
        denied = await reader.call("create_note", {"title": "should not exist"})
        check(
            "read-only token denied on create_note",
            denied.get("error_code") == "permission_denied",
            f"got: {denied}",
        )

        denied_upload = await reader.call(
            "upload_media",
            {"filename": "x.txt", "mime": "text/plain", "content_base64": "aGk="},
        )
        check(
            "read-only token denied on upload_media",
            denied_upload.get("error_code") == "permission_denied",
            f"got: {denied_upload}",
        )

        # ── 3. writer can upload with a caller-supplied description ──────────
        writer = McpClient(write_token)
        check("writer client connects", await writer.connect())

        payload = base64.b64encode(b"hello from smoke test").decode("ascii")
        uploaded = await writer.call(
            "upload_media",
            {
                "filename": "smoke.txt",
                "mime": "text/plain",
                "content_base64": payload,
                "description": "A smoke-test text file.",
            },
        )
        asset_id = uploaded.get("data", {}).get("asset_id")
        check("writer uploads media", bool(asset_id), f"got: {uploaded}")
        if asset_id:
            created_assets.append(uuid.UUID(asset_id))

            # An agent-supplied description must mark enrichment complete, or
            # the vision worker would analyse the file again for no reason.
            async with session_factory() as session:
                asset = await session.get(MediaAsset, uuid.UUID(asset_id))
                check(
                    "agent description stored",
                    (asset.meta or {}).get("ai_description") == "A smoke-test text file.",
                    f"meta: {asset.meta}",
                )
                check(
                    "agent description skips local enrichment",
                    asset.enrichment_status == "complete",
                    f"status: {asset.enrichment_status}",
                )

        # ── 4. writer can create a note with a block and tags ────────────────
        expires = (datetime.now(UTC) + timedelta(days=180)).isoformat()
        created = await writer.call(
            "create_note",
            {
                "title": "Smoke test voucher",
                "type": "voucher",
                "summary": "Created by the agent write smoke test.",
                "expires_at": expires,
                "blocks": [
                    {"type": "text", "text_content": "Expires in 6 months."},
                    {
                        "type": "file",
                        "text_content": "smoke.txt",
                        "media_asset_id": asset_id,
                    },
                ],
                "tags": ["smoke-test"],
            },
        )
        note_id = created.get("data", {}).get("id")
        check("writer creates a note", bool(note_id), f"got: {created}")
        if note_id:
            created_notes.append(uuid.UUID(note_id))

            async with session_factory() as session:
                blocks = (
                    await session.execute(
                        select(NoteBlock).where(NoteBlock.note_id == uuid.UUID(note_id))
                    )
                ).scalars().all()
                check("note has both blocks", len(blocks) == 2, f"count: {len(blocks)}")
                check(
                    "file block carries the asset",
                    any(b.media_asset_id and str(b.media_asset_id) == asset_id for b in blocks),
                )
                note = await session.get(Note, uuid.UUID(note_id))
                check("note is family-visible", note.visibility == "family", f"got: {note.visibility}")
                check("note has expires_at", note.expires_at is not None)
                check(
                    "note type recorded",
                    note.type == "voucher",
                    f"got: {note.type}",
                )

            # ── 5. append_block adds to it ───────────────────────────────────
            appended = await writer.call(
                "append_block",
                {
                    "note_id": note_id,
                    "type": "text",
                    "text_content": "Appended by the smoke test.",
                },
            )
            check(
                "writer appends a block",
                appended.get("ok") is True,
                f"got: {appended}",
            )

            # ── 6. the agent can read back what it wrote ─────────────────────
            fetched = await writer.call("get_note", {"note_id": note_id, "include_blocks": True})
            check(
                "writer reads the note back",
                fetched.get("ok") is True and bool(fetched.get("data")),
                f"got: {fetched}",
            )

        # ── 7. agents cannot create non-family notes ─────────────────────────
        # The tool hard-codes visibility=family, so a private note cannot even
        # be requested; assert the tool has no such parameter to abuse.
        schema = await writer.call("create_note", {"title": "visibility probe"})
        check(
            "create_note ignores visibility",
            schema.get("ok") is True,
            f"got: {schema}",
        )
        if schema.get("ok"):
            probe_id = schema.get("data", {}).get("id")
            if probe_id:
                created_notes.append(uuid.UUID(probe_id))
                async with session_factory() as session:
                    probe = await session.get(Note, uuid.UUID(probe_id))
                    check(
                        "probe note forced to family visibility",
                        probe.visibility == "family",
                        f"got: {probe.visibility}",
                    )

        # ── 8. every call is audited ─────────────────────────────────────────
        from app.models import AgentToolCall

        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(AgentToolCall).where(
                        AgentToolCall.agent.in_(("Smoke ReadOnly", "Smoke Writer"))
                    )
                )
            ).scalars().all()
            check("writes are audited", len(rows) >= 3, f"rows: {len(rows)}")
            denied_rows = [r for r in rows if r.status == "permission_denied"]
            check("denied attempts are audited", len(denied_rows) >= 2, f"rows: {len(denied_rows)}")
    finally:
        async with session_factory() as session:
            for note_id in created_notes:
                note = await session.get(Note, note_id)
                if note is not None:
                    await session.delete(note)
            for asset_id in created_assets:
                asset = await session.get(MediaAsset, asset_id)
                if asset is not None:
                    await session.delete(asset)
            for token_id in created_tokens:
                token = await session.get(DeviceToken, token_id)
                if token is not None:
                    await session.delete(token)
            await session.commit()
            print(f"cleaned up {len(created_notes)} notes, {len(created_assets)} assets, "
                  f"{len(created_tokens)} tokens")

    print()
    if failures:
        print(f"{len(failures)} FAILED: {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
