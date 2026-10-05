"""MCP server exposing the household agent tools.

The Model Context Protocol lets an agent discover and call tools without a
bespoke HTTP client per agent. This module serves the **same** tools as
``/internal/agent`` — it reads ``app.agent.registry``, so there is one definition
of what a tool is and no drift between the two surfaces.

Authentication reuses the device tokens from ``services/agent_tokens.py``: the
MCP layer verifies the bearer token and stashes the agent identity, and each tool
call re-resolves it to build the same ``Actor`` the REST path builds. A client
cannot widen its own scope by naming it in the request.

Mounting is handled by ``app.main``; the session manager's lifespan is entered
there. Note ``streamable_http_path="/"`` so the server answers at the mount point
itself (``/mcp``) rather than ``/mcp/mcp``.
"""

from __future__ import annotations

import contextlib
import inspect
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer

from app.agent.executor import execute_tool
from app.agent.registry import ToolContext, registry
from app.api.deps import Actor
from app.core.db import session_factory
from app.models import Household
from app.services.agent_tokens import resolve_agent_token

logger = structlog.get_logger(__name__)

MCP_SERVER_NAME = "familyos"
MCP_MOUNT_PATH = "/mcp"
MCP_PUBLIC_BASE_URL = "https://familyos.logeebox.com"


class DeviceTokenVerifier:
    """Verifies MCP bearer tokens against the ``device_tokens`` table.

    Implements the SDK's ``TokenVerifier`` protocol. Returning ``None`` for any
    unusable token (unknown, revoked, expired) keeps the failure modes
    indistinguishable to the caller.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        async with session_factory() as session:
            identity = await resolve_agent_token(session, token)
            if identity is None:
                return None
            return AccessToken(
                token=token,
                client_id=identity.agent_name,
                scopes=sorted(identity.scopes),
                subject=str(identity.member_id) if identity.member_id else None,
                claims={"household_id": str(identity.household_id)},
            )


def _register_tools(server: MCPServer) -> None:
    """Mirror every read-only registry entry as an MCP tool.

    The MCP SDK derives a tool's JSON schema from the handler's signature, so the
    signature is synthesised from the registry's params model. Passing
    ``Annotated`` types through preserves the model's constraints (``ge``,
    ``max_length``, …) in the published schema rather than flattening them to
    bare types.
    """

    for name, definition in registry.items():
        if definition.mutates:
            # Write tools are deliberately not exposed over MCP yet. A remote
            # agent should not be able to change household data without an
            # explicit confirmation flow, which does not exist here.
            logger.info("mcp_tool_skipped_mutating", tool=name)
            continue

        handler = _make_handler(name, definition)
        handler.__name__ = name
        handler.__signature__ = _signature_from_model(definition.params_model)
        server.add_tool(handler, name=name, description=definition.description)


def _signature_from_model(params_model: type) -> inspect.Signature:
    from typing import Annotated

    parameters = []
    for field_name, field in params_model.model_fields.items():
        annotation = Annotated[field.annotation, *field.metadata]
        default = (
            inspect.Parameter.empty
            if field.is_required()
            else field.get_default(call_default_factory=True)
        )
        parameters.append(
            inspect.Parameter(
                field_name,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=annotation,
                default=default,
            )
        )
    return inspect.Signature(parameters)


def _make_handler(name: str, definition):
    """Build the MCP handler for one registry tool.

    The handler receives only validated keyword arguments — no request object —
    so the calling agent's identity is read from the access token the MCP layer
    verified for this request.
    """

    async def handler(**kwargs: Any) -> Any:
        from mcp.server.auth.middleware.auth_context import get_access_token

        access_token = get_access_token()
        if access_token is None:
            return {"ok": False, "error": "Not authenticated", "error_code": "unauthenticated"}

        # Re-resolve the token on every call rather than trusting the claims
        # cached at session start: a token revoked mid-session must stop working
        # immediately, which is the whole point of per-agent tokens.
        async with session_factory() as session:
            identity = await resolve_agent_token(session, access_token.token)
            if identity is None:
                return {"ok": False, "error": "Invalid agent token", "error_code": "unauthenticated"}

            actor = await _build_actor(session, identity)
            if actor is None:
                return {"ok": False, "error": "Invalid agent token", "error_code": "unauthenticated"}

            context = ToolContext(
                actor=actor,
                session=session,
                request_id=str(uuid.uuid4()),
                agent=identity.agent_name,
            )
            result = await execute_tool(name=name, params=kwargs, context=context)

        # Return plain JSON: MCP serialises dicts into structured content, and a
        # ToolResult is not itself JSON-serialisable.
        if result.ok:
            return {"ok": True, "data": _jsonable(result.data), "meta": result.meta}
        return {"ok": False, "error": result.error, "error_code": result.error_code}

    return handler


async def _build_actor(session, identity) -> Actor | None:
    household = await session.get(Household, identity.household_id)
    if household is None:
        return None
    return Actor(
        member_id=identity.member_id,
        household_id=identity.household_id,
        role="agent",
        display_name=identity.label,
        timezone=household.timezone,
        locale=household.locale,
        scopes=identity.scopes,
    )


def _jsonable(value: Any) -> Any:
    """Convert Pydantic models and ORM rows into JSON-safe structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return _jsonable(dump(mode="json"))
    return str(value)


def build_mcp_server(*, public_base_url: str) -> MCPServer:
    """Create the MCP server with the household tools registered.

    ``token_verifier`` and ``auth`` must be supplied together — the SDK rejects
    one without the other. ``auth`` does not start an OAuth flow here (no
    ``auth_server_provider``); it only publishes the protected-resource metadata
    document and enables the bearer middleware. ``validate_token_resource`` is
    off because our verifier decides validity from the database, not from a
    resource indicator.
    """

    server = MCPServer(
        name=MCP_SERVER_NAME,
        title="FamilyOS",
        instructions=(
            "Household notes and tags. Read-only: these tools never change data. "
            "Notes marked private to another member are not visible."
        ),
        token_verifier=DeviceTokenVerifier(),
        auth=AuthSettings(
            issuer_url=public_base_url,
            resource_server_url=public_base_url,
            validate_token_resource=False,
        ),
    )
    _register_tools(server)
    return server


mcp_server = build_mcp_server(public_base_url=MCP_PUBLIC_BASE_URL)


@contextlib.asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Run the MCP session manager for the lifetime of the parent app.

    The MCP streamable-HTTP transport keeps sessions in a task group that must be
    running for the mounted app to serve requests. Mounting without this yields a
    server that answers every call with a 500.
    """

    async with mcp_server.session_manager.run():
        yield
