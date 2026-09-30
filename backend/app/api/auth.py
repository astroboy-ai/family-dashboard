from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_actor
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import create_access_token, verify_password
from app.models import FamilyMember, Household, User


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


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
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
        path="/",
    )
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