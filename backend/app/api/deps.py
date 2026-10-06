import uuid
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import decode_access_token
from app.models import FamilyMember, Household, User


ROLE_SCOPES: dict[str, set[str]] = {
    "parent": {
        "notes.read",
        "notes.write",
        "notes.read.secrets",
        "calendar.read",
        "calendar.write",
        "calendar.manage",
        "calendar.admin",
        "admin.members",
        "admin.devices",
    },
    "child": {"notes.read.own", "notes.write.own", "calendar.read"},
    "guest": {"notes.read.shared", "calendar.read"},
    "device": {"calendar.read"},
    # Agents (Hermes, Kururu) authenticate with a device token, not a session.
    # Their real scopes come from the token row, so this entry is intentionally
    # empty: it exists so `role` is never an unknown key. Do NOT add scopes here
    # — a role-based grant would let every agent inherit them.
    "agent": set(),
}


class Actor(BaseModel):
    model_config = ConfigDict(frozen=True)

    # None for an agent token that acts for the household rather than as a
    # specific family member. `note_access_clause` treats a missing member as
    # "owns nothing", so such a caller sees shared notes only.
    member_id: uuid.UUID | None = None
    household_id: uuid.UUID
    role: str
    display_name: str
    timezone: str
    locale: str
    scopes: frozenset[str] = Field(default_factory=frozenset)


async def get_current_actor(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Actor:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        claims = decode_access_token(token, settings=settings)
        member_id = uuid.UUID(claims["sub"])
        household_id = uuid.UUID(claims["household_id"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from error

    statement = (
        select(FamilyMember, User, Household)
        .outerjoin(User, User.id == FamilyMember.user_id)
        .join(Household, Household.id == FamilyMember.household_id)
        .where(
            FamilyMember.id == member_id,
            FamilyMember.household_id == household_id,
            FamilyMember.is_active.is_(True),
            or_(FamilyMember.user_id.is_(None), User.is_active.is_(True)),
        )
    )
    result = await session.execute(statement)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    member, _, household = row
    extra_scopes: Any = member.permissions.get("scopes", [])
    validated_extra_scopes = (
        {scope for scope in extra_scopes if isinstance(scope, str)}
        if isinstance(extra_scopes, (list, tuple, set))
        else set()
    )
    scopes = ROLE_SCOPES.get(member.role, set()) | validated_extra_scopes
    return Actor(
        member_id=member.id,
        household_id=member.household_id,
        role=member.role,
        display_name=member.display_name,
        timezone=household.timezone,
        locale=household.locale,
        scopes=frozenset(scopes),
    )


def require_scope(scope: str):
    async def dependency(actor: Annotated[Actor, Depends(get_current_actor)]) -> Actor:
        if scope not in actor.scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return actor

    return dependency


def require_role(*roles: str):
    async def dependency(actor: Annotated[Actor, Depends(get_current_actor)]) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return actor

    return dependency