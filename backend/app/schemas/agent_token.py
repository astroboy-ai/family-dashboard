"""Schemas for admin agent-token management.

A token's plaintext exists exactly once, in the response to the mint call. The
list and revoke responses describe tokens without ever carrying a value that
could be replayed, and ``token_hash`` is not exposed at all — it is a lookup key,
not something an operator needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Kept in step with what the executor and the MCP server actually enforce. A
# scope that grants nothing would be a lie in the UI.
KNOWN_SCOPES: dict[str, str] = {
    "notes.read": "Search and read family-visible notes",
    "notes.write": "Create notes, append blocks, upload media",
    "calendar.read": "Read calendar events",
    "calendar.write": "Create and modify calendar events",
}


class AgentTokenCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(min_length=1)
    # Null means the token never expires. Expressed in days rather than a date so
    # the caller does not have to reason about timezones.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    member_id: uuid.UUID | None = None

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Label cannot be blank")
        return cleaned

    @field_validator("scopes")
    @classmethod
    def known_scopes_only(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(KNOWN_SCOPES))
        if unknown:
            raise ValueError(f"Unknown scope(s): {', '.join(unknown)}")
        # De-duplicate while keeping the caller's order, so the UI shows what
        # they picked rather than an arbitrary set ordering.
        return list(dict.fromkeys(value))


class AgentTokenResponse(BaseModel):
    """A token as listed. Never includes the plaintext or its hash."""

    id: uuid.UUID
    label: str
    scopes: list[str]
    member_id: uuid.UUID | None = None
    created_at: datetime
    expires_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    # Derived server-side so the UI does not have to compare timestamps against
    # a clock that may not be the server's.
    is_active: bool
    is_expired: bool


class AgentTokenCreatedResponse(AgentTokenResponse):
    """The mint response. ``token`` is shown once and never stored."""

    token: str
    warning: str = (
        "Copy this token now. It is not stored in a readable form and cannot be "
        "shown again."
    )
