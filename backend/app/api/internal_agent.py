"""Internal agent API: tool discovery and invocation for trusted agents.

Authentication is a **device token**, resolved server-side to a household and a
set of scopes. The request body names the tool and its parameters — it never
names the caller. An earlier design accepted ``household_id`` and
``actor_member_id`` from the body, which meant any holder of the shared service
token could act as any family member, including a parent. Identity now comes
only from the token, so one agent can be revoked without touching another.

Every invocation is written to ``agent_tool_calls`` for audit.
"""

import uuid
from typing import Annotated, Any

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.executor import execute_tool
from app.agent.registry import ToolContext, ToolResult, registry
from app.agent import tools as registered_tools
from app.api.deps import Actor
from app.core.db import get_session
from app.models import Household
from app.services.agent_tokens import AgentIdentity, resolve_agent_token, touch_agent_token


router = APIRouter(prefix="/internal/agent", tags=["internal-agent"])
bearer_scheme = HTTPBearer(auto_error=False)


class ToolInvocationRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def require_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentIdentity:
    """Resolve the bearer token to an agent identity.

    Deliberately returns the same 401 for unknown, revoked and expired tokens so
    the response does not reveal which tokens exist.
    """

    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing agent token")

    identity = await resolve_agent_token(session, credentials.credentials)
    if identity is None:
        raise _unauthorized("Invalid agent token")
    return identity


async def load_actor(
    *,
    session: AsyncSession,
    identity: AgentIdentity,
) -> Actor:
    """Build the Actor for a token.

    The household comes from the token's own row and the scopes are the token's
    own — not a role's. There is no path for the caller to widen either.
    """

    household = await session.get(Household, identity.household_id)
    if household is None:
        raise _unauthorized("Invalid agent token")

    return Actor(
        member_id=identity.member_id,
        household_id=identity.household_id,
        role="agent",
        display_name=identity.label,
        timezone=household.timezone,
        locale=household.locale,
        scopes=identity.scopes,
    )


@router.get("/tools", dependencies=[Depends(require_agent)])
async def list_agent_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "parameters": tool.params_model.model_json_schema(),
            "mutates": tool.mutates,
            "permissions": list(tool.permissions),
        }
        for tool in sorted(registry.values(), key=lambda item: item.name)
    ]


@router.get("/instructions", dependencies=[Depends(require_agent)])
async def get_agent_instructions() -> dict[str, str]:
    """Return the AGENTS.md content for agent reference.

    Agents call this endpoint to discover how to use the system.
    The instructions file is the single source of truth — when it is
    updated, all agents immediately see the change on next call.
    """
    agents_md = Path(__file__).resolve().parents[3] / "AGENTS.md"
    try:
        return {"instructions": agents_md.read_text(encoding="utf-8")}
    except FileNotFoundError:
        return {"instructions": "AGENTS.md not found. Contact the system administrator."}


@router.get("/tools/{name}/schema", dependencies=[Depends(require_agent)])
async def get_tool_schema(name: str) -> dict[str, Any]:
    tool = registry.get(name)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool.params_model.model_json_schema()


@router.post("/tools/{name}", response_model=ToolResult)
async def invoke_tool(
    name: str,
    payload: ToolInvocationRequest,
    request: Request,
    identity: Annotated[AgentIdentity, Depends(require_agent)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ToolResult:
    actor = await load_actor(session=session, identity=identity)
    context = ToolContext(
        actor=actor,
        session=session,
        request_id=request.headers.get("X-Request-ID", str(uuid.uuid4())),
        # Record which token called, so the audit log can tell the agents apart.
        agent=identity.agent_name,
    )
    result = await execute_tool(name=name, params=payload.params, context=context)

    # Best-effort: failing to record last-seen must not fail the tool call.
    try:
        await touch_agent_token(session, identity.token_id)
        await session.commit()
    except Exception:
        await session.rollback()

    return result
