import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RefreshToken(Base):
    """A long-lived session credential, stored hashed and rotated on use.

    Only the SHA-256 of the token is persisted: a database leak must not hand an
    attacker a usable session. ``rotated_at`` marks a token that has already been
    exchanged; presenting one again is treated as theft and revokes the whole
    family of tokens (see ``app.services.sessions``).
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash", unique=True),
        Index("ix_refresh_tokens_member_active", "member_id", "expires_at"),
        Index(
            "ix_refresh_tokens_family",
            "family_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    # Every rotation keeps the original family_id so a replayed token can revoke
    # the entire chain, not just the one row.
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    # Set when a rotated token is presented again — kept for the audit trail.
    reuse_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
