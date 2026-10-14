import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    Computed,
    DateTime,
    ForeignKey,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ArchifyDiagram(Base):
    """An Archify interactive HTML diagram, stored as a standalone document.

    Agents generate these with the Archify skill (bin/archify.mjs finalize) and
    hand the finished HTML to create_archify_diagram. The HTML is stored
    verbatim — the viewer renders it in a sandboxed iframe, never as a route.
    """

    __tablename__ = "archify_diagrams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(String(40))
    html: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # Plain text pulled out of the HTML by the API layer, so the tsvector can
    # index what a reader would recognise without shipping a HTML parser to PG.
    search_tokens_text: Mapped[str | None] = mapped_column(Text)
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(type, '')), 'B') || "
            "to_tsvector('simple', coalesce(search_tokens_text, ''))",
            persisted=True,
        ),
    )


archify_diagram_tags = Table(
    "archify_diagram_tags",
    Base.metadata,
    Column(
        "diagram_id",
        UUID(as_uuid=True),
        ForeignKey("archify_diagrams.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "applied_by",
        UUID(as_uuid=True),
        ForeignKey("family_members.id", ondelete="SET NULL"),
    ),
    Column(
        "applied_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)
