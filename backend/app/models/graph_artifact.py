import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GraphArtifact(Base):
    """An imported Archify artifact — a self-contained interactive HTML file.

    Archify output is produced outside FamilyOS (by 萬事屋 / Kururu) and handed
    over as a single HTML file that carries its own JS: motion, search, trace.
    Re-rendering it natively would throw that away, so the file is stored as-is
    and displayed in a sandboxed iframe.

    This is deliberately *not* a ``graph_views`` row: a view is a saved
    configuration that FamilyOS renders itself, an artifact is opaque content
    FamilyOS only displays. Keeping them apart means an import cannot break the
    native graph page, and a view can be edited without touching a file.
    """

    __tablename__ = "graph_artifacts"
    __table_args__ = (
        Index("ix_graph_artifacts_household_order", "household_id", "order_index"),
        Index("ix_graph_artifacts_household_created", "household_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # 'html' | 'png' | 'svg' | 'json' — html is the interactive case and the only
    # one that needs the iframe sandbox.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="html", server_default="html")
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    # Who or what produced it: 'manual' | 'agent' | a free-form producer name.
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual", server_default="manual")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id", ondelete="SET NULL")
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
