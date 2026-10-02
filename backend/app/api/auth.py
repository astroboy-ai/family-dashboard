from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import create_access_token, hash_password, verify_password
from app.models import FamilyMember, Household, User


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class PinLoginRequest(BaseModel):
    member_id: UUID
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class SetPinRequest(BaseModel):
    member_id: UUID | None = None
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class SetupRequest(BaseModel):
    household_name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(min_length=1, max_length=64)
    locale: str = Field(default="en", min_length=2, max_length=16)
    week_starts_on: str = Field(default="monday", pattern=r"^(monday|sunday|saturday)$")
    display_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    pin: str = Field(min_length=4, max_length=6, pattern=r"^\d{4,6}$")
    ai_provider: str = Field(default="none", pattern=r"^(none|ollama|openai)$")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown timezone") from error
        return value


def set_access_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
        path="/",
    )


@router.get("/members")
async def list_login_members(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, list[dict[str, object]]]:
    statement = (
        select(FamilyMember)
        .where(
            FamilyMember.is_active.is_(True),
            FamilyMember.role.in_(("parent", "child", "guest")),
        )
        .order_by(FamilyMember.created_at, FamilyMember.display_name)
    )
    result = await session.execute(statement)
    members = result.scalars().all()
    return {
        "items": [
            {
                "id": str(member.id),
                "display_name": member.display_name,
                "avatar": str(member.avatar_media_id) if member.avatar_media_id else None,
                "has_pin": member.pin_hash is not None,
            }
            for member in members
        ]
    }


@router.post("/pin-login")
async def pin_login(
    payload: PinLoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    statement = (
        select(FamilyMember, Household)
        .join(Household, Household.id == FamilyMember.household_id)
        .where(FamilyMember.id == payload.member_id, FamilyMember.is_active.is_(True))
        .with_for_update()
    )
    result = await session.execute(statement)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid member or PIN")

    member, _ = row
    now = datetime.now(UTC)
    if member.pin_locked_until is not None:
        if member.pin_locked_until > now:
            retry_after = max(1, int((member.pin_locked_until - now).total_seconds()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        member.pin_locked_until = None
        member.pin_failed_attempts = 0

    if member.pin_hash is None or not verify_password(payload.pin, member.pin_hash):
        member.pin_failed_attempts += 1
        if member.pin_failed_attempts >= 5:
            member.pin_locked_until = now + timedelta(seconds=60)
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again in 60 seconds.",
                headers={"Retry-After": "60"},
            )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid member or PIN")

    member.pin_failed_attempts = 0
    member.pin_locked_until = None
    await session.commit()
    token = create_access_token(
        member_id=str(member.id),
        household_id=str(member.household_id),
        settings=settings,
    )
    set_access_cookie(response, token, settings)
    return {"member_id": str(member.id), "role": member.role}


@router.post("/pin", status_code=status.HTTP_204_NO_CONTENT)
async def set_member_pin(
    payload: SetPinRequest,
    response: Response,
    actor: Annotated[Actor, Depends(get_current_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    member_id = payload.member_id or actor.member_id
    if member_id != actor.member_id and actor.role != "parent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    result = await session.execute(
        select(FamilyMember)
        .where(
            FamilyMember.id == member_id,
            FamilyMember.household_id == actor.household_id,
            FamilyMember.is_active.is_(True),
            FamilyMember.role.in_(("parent", "child", "guest")),
        )
        .with_for_update()
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family member not found")
    member.pin_hash = hash_password(payload.pin)
    member.pin_failed_attempts = 0
    member.pin_locked_until = None
    await session.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    normalized_email = payload.email.strip().casefold()
    statement = (
        select(User, FamilyMember, Household)
        .join(FamilyMember, FamilyMember.user_id == User.id)
        .join(Household, Household.id == FamilyMember.household_id)
        .where(
            func.lower(User.email) == normalized_email,
            User.is_active.is_(True),
            FamilyMember.is_active.is_(True),
        )
    )
    result = await session.execute(statement)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    user, member, _ = row
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    access_token = create_access_token(
        member_id=str(member.id),
        household_id=str(member.household_id),
        settings=settings,
    )
    set_access_cookie(response, access_token, settings)
    return {"member_id": str(member.id), "role": member.role}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key="access_token", path="/")
    return response


@router.get("/me")
async def get_me(
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> dict[str, object]:
    return {
        "member_id": str(actor.member_id),
        "household_id": str(actor.household_id),
        "display_name": actor.display_name,
        "role": actor.role,
        "timezone": actor.timezone,
        "locale": actor.locale,
        "scopes": sorted(actor.scopes),
    }


@router.get("/setup-status")
async def get_setup_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, bool]:
    result = await session.execute(select(func.count()).select_from(FamilyMember))
    return {"available": result.scalar_one() == 0}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def complete_setup(
    payload: SetupRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    await session.execute(text("SELECT pg_advisory_xact_lock(639721305)"))
    count_result = await session.execute(select(func.count()).select_from(FamilyMember))
    if count_result.scalar_one() > 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup is already complete")

    household = Household(
        id=uuid4(),
        name=payload.household_name.strip(),
        timezone=payload.timezone,
        locale=payload.locale,
        week_starts_on=payload.week_starts_on,
        settings={"ai_provider": payload.ai_provider},
    )
    user = User(
        id=uuid4(),
        email=payload.email.strip().casefold(),
        password_hash=hash_password(payload.password),
    )
    member = FamilyMember(
        id=uuid4(),
        household_id=household.id,
        user_id=user.id,
        display_name=payload.display_name.strip(),
        role="parent",
        pin_hash=hash_password(payload.pin),
    )
    session.add_all((household, user, member))
    await session.commit()

    token = create_access_token(
        member_id=str(member.id),
        household_id=str(household.id),
        settings=settings,
    )
    set_access_cookie(response, token, settings)
    return {"member_id": str(member.id), "role": member.role}