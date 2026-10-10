from collections.abc import AsyncIterator
import uuid

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.agent.executor import execute_tool
from app.agent.registry import ToolContext, registry
from app.api.deps import Actor
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.main import create_app


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_count += 1


async def unused_probe() -> None:
    return None


def make_actor(scopes: set[str]) -> Actor:
    return Actor(
        member_id=uuid.uuid4(),
        household_id=uuid.uuid4(),
        role="parent",
        display_name="Parent",
        timezone="UTC",
        locale="en",
        scopes=frozenset(scopes),
    )


async def test_internal_tool_catalog_requires_service_token() -> None:
    settings = Settings(
        jwt_secret="test-only-secret-long-enough-for-hs256",
        service_token="internal-test-token",
    )
    app = create_app(settings=settings, readiness_probes={"database": unused_probe})
    app.dependency_overrides[get_settings] = lambda: settings

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/internal/agent/tools")
        allowed = await client.get(
            "/internal/agent/tools",
            headers={"Authorization": "Bearer internal-test-token"},
        )

    assert denied.status_code == 401
    assert allowed.status_code == 200
    tools = {tool["name"]: tool for tool in allowed.json()}
    assert "search_notes" in tools
    assert "get_note" in tools
    assert "parameters" in tools["get_note"]


async def test_executor_checks_scopes_and_audits_redacted_params() -> None:
    actor = make_actor(set())
    session = RecordingSession()
    context = ToolContext(actor=actor, session=session, request_id="test-request")

    result = await execute_tool(
        name="search_notes",
        params={"query": "secret phrase", "pin": "1234"},
        context=context,
    )

    assert result.ok is False
    assert result.error_code == "permission_denied"
    assert session.commit_count == 1
    log_entry = session.added[0]
    assert log_entry.status == "permission_denied"
    assert log_entry.params["pin"] == "[redacted]"


async def test_executor_rejects_unknown_tools_without_leaking_details() -> None:
    actor = make_actor({"notes.read"})
    session = RecordingSession()
    context = ToolContext(actor=actor, session=session, request_id="test-request")

    result = await execute_tool(name="not_a_tool", params={}, context=context)

    assert result.ok is False
    assert result.error_code == "not_found"