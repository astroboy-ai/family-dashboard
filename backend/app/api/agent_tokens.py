"""Admin routes for managing agent device tokens.

Minting, listing and revoking the tokens that non-human callers use to reach the
MCP server. These routes are protected by cookie authentication (see
``get_current_actor``), which means an *agent* cannot reach them: an agent
presents a bearer token, and bearer tokens are never read for these endpoints.
That is the property that keeps scope escalation impossible — a token holder
cannot mint itself a wider token.

The plaintext token is returned exactly once, from the mint call. Only its
SHA-256 hash is stored, so it cannot be recovered afterwards; the remedy for a
lost token is to revoke it and mint another.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import require_admin
from app.api.deps import Actor, get_current_actor
from app.core.db import get_session
from app.models import DeviceToken, FamilyMember
from app.schemas.agent_token import (
    KNOWN_SCOPES,
    AgentTokenCreateRequest,
    AgentTokenCreatedResponse,
    AgentTokenResponse,
)
from app.services.agent_tokens import generate_token, hash_token

router = APIRouter(prefix="/admin/agent-tokens", tags=["admin", "agent-tokens"])


def _describe(record: DeviceToken, *, now: datetime) -> AgentTokenResponse:
    """Serialise a token row without exposing anything replayable."""

    expired = record.expires_at is not None and record.expires_at <= now
    return AgentTokenResponse(
        id=record.id,
        label=record.label,
        scopes=list(record.scopes or []),
        member_id=record.member_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_seen_at=record.last_seen_at,
        revoked_at=record.revoked_at,
        is_active=record.revoked_at is None and not expired,
        is_expired=expired,
    )


@router.get("/scopes")
async def list_known_scopes(
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> dict[str, str]:
    """The scopes an operator may grant, with a human description each.

    Served rather than hard-coded in the frontend so the UI cannot offer a scope
    the backend would reject.
    """

    require_admin(actor)
    return KNOWN_SCOPES


@router.get("")
async def list_agent_tokens(
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AgentTokenResponse]:
    """Every token in the household, newest first, revoked ones included.

    Revoked and expired tokens are kept in the list on purpose: an operator
    needs to see that a token was killed, not have it silently disappear.
    """

    require_admin(actor)
    now = datetime.now(UTC)
    records = (
        (
            await session.execute(
                select(DeviceToken)
                .where(DeviceToken.household_id == actor.household_id)
                .order_by(DeviceToken.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_describe(record, now=now) for record in records]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent_token(
    payload: AgentTokenCreateRequest,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentTokenCreatedResponse:
    """Mint a token. The plaintext is in this response and nowhere else."""

    require_admin(actor)

    if payload.member_id is not None:
        member = (
            await session.execute(
                select(FamilyMember).where(
                    FamilyMember.id == payload.member_id,
                    FamilyMember.household_id == actor.household_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this household",
            )

    token = generate_token()
    record = DeviceToken(
        id=uuid.uuid4(),
        household_id=actor.household_id,
        member_id=payload.member_id,
        label=payload.label,
        token_hash=hash_token(token),
        scopes=payload.scopes,
        expires_at=(
            datetime.now(UTC) + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days is not None
            else None
        ),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return AgentTokenCreatedResponse(
        **_describe(record, now=datetime.now(UTC)).model_dump(),
        token=token,
    )


@router.delete("/{token_id}")
async def revoke_agent_token(
    token_id: uuid.UUID,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    """Revoke a token by stamping ``revoked_at``.

    A soft revoke, not a delete: the audit rows in ``agent_tool_calls`` reference
    the token, and the resolution path already refuses a stamped token on every
    call, so revocation takes effect immediately.
    """

    require_admin(actor)

    record = (
        await session.execute(
            select(DeviceToken).where(
                DeviceToken.id == token_id,
                DeviceToken.household_id == actor.household_id,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        await session.commit()

    return {"id": str(record.id), "revoked": True}
