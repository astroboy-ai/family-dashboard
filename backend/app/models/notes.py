import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('family', 'parents', 'private')", name="visibility_valid"
        ),
        Index(
            "ix_notes_household_status_updated",
            "household_id",
            "status",
            text("updated_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_notes_household_expires",
            "household_id",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("ix_notes_extra_gin", "extra", postgresql_using="gin", postgresql_ops={"extra": "jsonb_path_ops"}),
        Index("ix_notes_search_tsv_gin", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(40), nullable=False, default="freeform", server_default="freeform")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="inbox", server_default="inbox")
    summary: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")
    )
    owner_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")
    )
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="family", server_default="family")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parent_note_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="SET NULL")
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    embedding_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(ai_summary, '')), 'C')",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NoteBlock(Base):
    __tablename__ = "note_blocks"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 0 AND 5", name="importance_range"),
        UniqueConstraint("note_id", "order_index", name="note_order_unique"),
        Index("ix_note_blocks_search_tsv_gin", "search_tsv", postgresql_using="gin"),
        Index(
            "ix_note_blocks_expires",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text)
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    thumb_media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    caption: Mapped[str | None] = mapped_column(Text)
    ai_description: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(text_content, '') || ' ' || "
            "coalesce(caption, '') || ' ' || coalesce(ai_description, '') || ' ' || "
            "coalesce(ocr_text, '') || ' ' || coalesce(transcript, ''))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


note_tags = Table(
    "note_tags",
    Base.metadata,
    Column("note_id", UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Column("source", String(16), nullable=False, server_default="human"),
    Column("confidence", Float),
    Column("model", String(120)),
    Column("evidence", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("applied_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("applied_by", UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")),
    Column("last_verified_at", DateTime(timezone=True)),
    Column("approved_by_human", Boolean, nullable=False, server_default=text("true")),
)