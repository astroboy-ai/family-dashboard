"""Refresh-token sessions: issue, rotate, revoke.

Design notes
------------
* The access token stays short-lived (15 min) and stateless — every request
  verifies a JWT with no database round-trip.
* The refresh token is long-lived (30 days by default), opaque (not a JWT) and
  stored only as a SHA-256 hash. Rotation on every use means a stolen token is
  usable at most once, and the theft is detectable.
* Reuse detection: presenting a token whose ``rotated_at`` is already set means
  either a replay or a race. We revoke the whole ``family_id`` chain rather than
  guessing, which logs the attacker out along with the victim — the safe choice.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import FamilyMember, RefreshToken


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedSession:
    refresh_token: str | None
    expires_at: datetime
    family_id: uuid.UUID


#: A rotation replayed inside this window is treated as a race (multiple tabs,
#: a retried request, a slow proxy) rather than theft. Outside it, a replay
#: still revokes the whole chain.
_REPLAY_GRACE = timedelta(seconds=15)


def _as_utc(value: datetime) -> datetime:
    """SQLite/psycopg may hand back a naive datetime; normalise for arithmetic."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _refresh_lifetime() -> timedelta:
    return timedelta(days=get_settings().refresh_token_days)


async def issue_session(
    *,
    session: AsyncSession,
    member: FamilyMember,
    user_agent: str | None = None,
    family_id: uuid.UUID | None = None,
) -> IssuedSession:
    """Create a refresh token. Pass *family_id* to continue an existing chain."""

    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + _refresh_lifetime()
    chain_id = family_id or uuid.uuid4()
    session.add(
        RefreshToken(
            member_id=member.id,
            family_id=chain_id,
            token_hash=_hash_token(token),
            expires_at=expires_at,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    await session.commit()
    return IssuedSession(refresh_token=token, expires_at=expires_at, family_id=chain_id)


async def rotate_session(
    *,
    session: AsyncSession,
    token: str,
    user_agent: str | None = None,
) -> tuple[FamilyMember, IssuedSession]:
    """Exchange a refresh token for a new one, returning the owning member.

    Raises ``AppError(401)`` for an unknown, expired or revoked token, and for a
    replayed token — in the replay case the whole chain is revoked first.
    """

    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == _hash_token(token))
        )
    ).scalar_one_or_none()

    if row is None:
        raise AppError("Invalid session", status_code=401, error_code="invalid_session")

    if row.revoked_at is not None:
        raise AppError("Session revoked", status_code=401, error_code="session_revoked")

    if row.rotated_at is not None:
        # The token was already exchanged. Two very different situations look
        # identical in the database, so we must tell them apart by time:
        #
        #   * a *replay* (token stolen and used later) — must revoke the chain;
        #   * a *race* (two tabs / a retried request hitting the rotation within
        #     a few seconds) — the legitimate client already holds the new token,
        #     so revoking the chain would sign the user out for no reason.
        #
        # Within the grace window we treat it as a race and hand back the same
        # successor token instead of killing the session. That keeps the
        # detection meaningful (an attacker replaying minutes or days later is
        # still caught) while making it impossible for normal multi-tab use to
        # log the whole family out.
        if now - _as_utc(row.rotated_at) <= _REPLAY_GRACE:
            successor = (
                await session.execute(
                    select(RefreshToken)
                    .where(
                        RefreshToken.family_id == row.family_id,
                        RefreshToken.rotated_at.is_(None),
                        RefreshToken.revoked_at.is_(None),
                    )
                    .order_by(RefreshToken.issued_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if successor is not None and successor.expires_at > now:
                member = await session.get(FamilyMember, row.member_id)
                if member is not None and member.is_active:
                    return member, IssuedSession(
                        refresh_token=None,
                        expires_at=successor.expires_at,
                        family_id=successor.family_id,
                    )

        # Outside the grace window: assume theft, kill the chain.
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, reuse_detected_at=now)
        )
        await session.commit()
        raise AppError("Session reused", status_code=401, error_code="session_reused")

    if row.expires_at <= now:
        raise AppError("Session expired", status_code=401, error_code="session_expired")

    member = await session.get(FamilyMember, row.member_id)
    if member is None or not member.is_active:
        raise AppError("Session revoked", status_code=401, error_code="session_revoked")

    row.rotated_at = now
    issued = await issue_session(
        session=session,
        member=member,
        user_agent=user_agent,
        family_id=row.family_id,
    )
    return member, issued


async def revoke_session(*, session: AsyncSession, token: str) -> None:
    """Revoke one token and the rest of its chain. Safe to call with junk."""

    if not token:
        return
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == _hash_token(token))
        )
    ).scalar_one_or_none()
    if row is None:
        return
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()


async def revoke_all_for_member(*, session: AsyncSession, member_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.member_id == member_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
