import hmac
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.executor import execute_tool
from app.agent.registry import ToolContext, ToolResult, registry
from app.agent import tools as registered_tools
from app.api.deps import ROLE_SCOPES, Actor
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.models import FamilyMember, Household, User


router = APIRouter(prefix="/internal/agent", tags=["internal-agent"])
bearer_scheme = HTTPBearer(auto_error=False)


class ToolInvocationRequest(BaseModel):
    household_id: uuid.UUID
    actor_member_id: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)


async def require_service_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.service_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent service is not configured")
    if credentials is None or not hmac.compare_digest(credentials.credentials, settings.service_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")


async def load_actor(
    *,
    session: AsyncSession,
    household_id: uuid.UUID,
    actor_member_id: uuid.UUID,
) -> Actor:
    statement = (
        select(FamilyMember, Household)
        .outerjoin(User, User.id == FamilyMember.user_id)
        .join(Household, Household.id == FamilyMember.household_id)
        .where(
            FamilyMember.id == actor_member_id,
            FamilyMember.household_id == household_id,
            FamilyMember.is_active.is_(True),
            or_(FamilyMember.user_id.is_(None), User.is_active.is_(True)),
        )
    )
    result = await session.execute(statement)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid actor")
    member, household = row
    extra_scopes = member.permissions.get("scopes", [])
    if not isinstance(extra_scopes, (list, tuple, set)):
        extra_scopes = []
    scopes = ROLE_SCOPES.get(member.role, set()) | {
        scope for scope in extra_scopes if isinstance(scope, str)
    }
    return Actor(
        member_id=member.id,
        household_id=member.household_id,
        role=member.role,
        display_name=member.display_name,
        timezone=household.timezone,
        locale=household.locale,
        scopes=frozenset(scopes),
    )


@router.get("/tools", dependencies=[Depends(require_service_token)])
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


@router.get("/tools/{name}/schema", dependencies=[Depends(require_service_token)])
async def get_tool_schema(name: str) -> dict[str, Any]:
    tool = registry.get(name)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool.params_model.model_json_schema()


@router.post("/tools/{name}", response_model=ToolResult, dependencies=[Depends(require_service_token)])
async def invoke_tool(
    name: str,
    payload: ToolInvocationRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ToolResult:
    actor = await load_actor(
        session=session,
        household_id=payload.household_id,
        actor_member_id=payload.actor_member_id,
    )
    context = ToolContext(
        actor=actor,
        session=session,
        request_id=request.headers.get("X-Request-ID", str(uuid.uuid4())),
    )
    return await execute_tool(name=name, params=payload.params, context=context)