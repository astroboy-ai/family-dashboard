"""Agent device tokens: identity and scopes for non-human callers.

An agent (Hermes, Kururu) presents an opaque token on the internal API. The token
is stored as a SHA-256 hash, so the database never holds anything that can be
replayed. Resolution returns the household plus the scopes the *token* carries —
the caller cannot name its own identity in the request body, which is what made
the previous design a privilege-escalation hole.

Design notes:

- The plaintext token is shown exactly once, at mint time. There is no way to
  read it back, matching how the rest of the stack treats secrets.
- ``member_id`` is nullable: an agent token belongs to the household and acts
  with the scopes it was granted, rather than impersonating a family member.
- Revocation and expiry are checked on every call, so a leaked token can be
  killed without rotating anything else.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeviceToken, Household

TOKEN_PREFIX = "fos_"
TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    """SHA-256 of the token. Deterministic, so it doubles as the lookup key."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """Mint a new opaque token. The caller must persist its hash."""
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


@dataclass(frozen=True)
class AgentIdentity:
    """What a valid agent token proves."""

    token_id: uuid.UUID
    household_id: uuid.UUID
    member_id: uuid.UUID | None
    label: str
    scopes: frozenset[str]

    @property
    def agent_name(self) -> str:
        """Short name for the audit row.

        Derived from the label so an operator can read the log, and stable
        because the label is set at mint time.
        """
        name = self.label.split("(")[0].strip()
        return name or self.label or "agent"


async def resolve_agent_token(
    session: AsyncSession,
    token: str,
    *,
    now: datetime | None = None,
) -> AgentIdentity | None:
    """Look up a token and return its identity, or None if it is not usable.

    A single query fetches the row and its household, so an unknown token costs
    one round-trip rather than two.
    """

    if not token:
        return None

    moment = now or datetime.now(UTC)
    statement = (
        select(DeviceToken, Household)
        .join(Household, Household.id == DeviceToken.household_id)
        .where(DeviceToken.token_hash == hash_token(token))
    )
    row = (await session.execute(statement)).first()
    if row is None:
        return None

    record, _household = row

    if record.revoked_at is not None:
        return None
    if record.expires_at is not None and record.expires_at <= moment:
        return None

    return AgentIdentity(
        token_id=record.id,
        household_id=record.household_id,
        member_id=record.member_id,
        label=record.label,
        scopes=frozenset(record.scopes or ()),
    )


async def touch_agent_token(session: AsyncSession, token_id: uuid.UUID) -> None:
    """Record last use. Best-effort: never let this fail a tool call."""

    record = await session.get(DeviceToken, token_id)
    if record is not None:
        record.last_seen_at = datetime.now(UTC)
