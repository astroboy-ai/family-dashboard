"""Vector embeddings for semantic retrieval.

One row per (owner, chunk, model). ``owner_type``/``owner_id`` point at either a
``notes`` row or a ``note_blocks`` row — blocks carry the OCR text, transcripts
and image descriptions, so they are usually the more useful retrieval unit.

Design notes (see CR-002):

* ``embedding`` is declared **without** a fixed dimension. pgvector only accepts
  a fixed width when a column is declared ``vector(N)``, and a declared width
  cannot be changed later while rows exist. Leaving it unconstrained means
  switching embedding models is a re-embed plus an index swap, not a column
  migration.
* ``dim`` and ``model`` are stored per row so several generations can coexist;
  ``is_active`` marks the rows produced by the currently configured model. The
  search layer filters on ``is_active`` so vectors from different models are
  never compared (mixing them silently produces nonsense rankings).
* The HNSW index is therefore a **partial expression** index —
  ``USING hnsw ((embedding::vector(N)) vector_cosine_ops) WHERE dim = N AND
  is_active``. pgvector refuses to index a dimension-less column directly
  (``column does not have dimensions``), but it accepts the cast, and the
  planner uses the index for the matching predicate. Changing N means dropping
  and recreating the index, which the ``embed.rebuild`` job does.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        CheckConstraint("owner_type IN ('note', 'block')", name="embeddings_owner_type_valid"),
        CheckConstraint("dim > 0", name="embeddings_dim_positive"),
        CheckConstraint("chunk_index >= 0", name="embeddings_chunk_index_non_negative"),
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "chunk_index",
            "model",
            name="embeddings_owner_chunk_model_unique",
        ),
        Index("ix_embeddings_household_owner", "household_id", "owner_type", "owner_id"),
        Index(
            "ix_embeddings_active",
            "household_id",
            "is_active",
            postgresql_where=text("is_active"),
        ),
        Index("ix_embeddings_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String(8), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # The exact text that was embedded. Kept so a rebuild can reuse it without
    # re-reading the source row, and so search results can quote the passage.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of the canonical content; lets the worker skip a re-embed when the
    # text has not changed (blueprint §9.4 idempotency).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
