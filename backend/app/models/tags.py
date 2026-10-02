import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("household_id", "slug", name="household_slug_unique"),
        CheckConstraint("kind IN ('system','facet','topic','adhoc')", name="kind_valid"),
        Index("ix_tags_household_kind_retired", "household_id", "kind", "retired_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="topic", server_default="topic")
    namespace: Mapped[str | None] = mapped_column(String(32))
    canonical_slug: Mapped[str | None] = mapped_column(String(120))
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ai_usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    proposed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    proposed_by: Mapped[str | None] = mapped_column(String(16))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TagExclusion(Base):
    __tablename__ = "tag_exclusions"
    __table_args__ = (
        CheckConstraint("scope IN ('note','note_type','member','household')", name="scope_valid"),
        Index("ix_tag_exclusions_household_slug", "household_id", "tag_slug"),
        Index("ix_tag_exclusions_household_scope_ref", "household_id", "scope", "scope_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE")
    )
    tag_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="note", server_default="note")
    scope_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scope_note_type: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(32), nullable=False, default="user_removed", server_default="user_removed")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TagProposal(Base):
    __tablename__ = "tag_proposals"
    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted','rejected','expired','auto_applied')", name="status_valid"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_tag_proposals_household_status_created", "household_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="SET NULL"))
    proposed_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    proposed_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="topic", server_default="topic")
    proposed_namespace: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TagAuditLog(Base):
    __tablename__ = "tag_audit_log"
    __table_args__ = (Index("ix_tag_audit_log_household_created", "household_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    note_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tag_slug: Mapped[str | None] = mapped_column(String(120))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class NoteRelation(Base):
    __tablename__ = "note_relations"
    __table_args__ = (
        UniqueConstraint(
            "from_note_id", "to_note_id", "relation_type", name="note_relation_unique"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    from_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    to_note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())