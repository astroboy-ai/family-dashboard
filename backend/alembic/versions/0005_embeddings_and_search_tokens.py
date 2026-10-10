"""Embeddings table, Chinese-aware search tokens, and the vector index.

Three related changes:

1. ``embeddings`` — one row per (owner, chunk, model). ``embedding`` is left
   dimension-less so switching models is a re-embed, not a column migration.
2. ``search_tokens_*`` columns on ``notes``/``note_blocks``. PostgreSQL's
   ``simple`` configuration does not segment CJK text, so tokens are produced in
   Python (jieba) and the ``tsvector`` columns are regenerated from them.
3. A partial expression HNSW index. pgvector refuses to index a dimension-less
   column directly, but accepts ``(embedding::vector(N))``; the partial
   predicate keeps the index valid when rows from other models are present.

The ``tsvector`` columns are ``GENERATED ALWAYS AS ... STORED`` and PostgreSQL
cannot alter a generated expression in place, so they are dropped and recreated.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_embeddings_and_search_tokens"
down_revision = "0004_tag_provenance_and_exclusions"
branch_labels = None
depends_on = None

DEFAULT_DIM = 768

NOTES_TSV = (
    "setweight(to_tsvector('simple', coalesce(search_tokens_title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(search_tokens_summary, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(search_tokens_ai_summary, '')), 'C')"
)

BLOCKS_TSV = (
    "to_tsvector('simple', coalesce(search_tokens_text, ''))"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- search tokens -----------------------------------------------------
    op.add_column("notes", sa.Column("search_tokens_title", sa.Text(), nullable=True))
    op.add_column("notes", sa.Column("search_tokens_summary", sa.Text(), nullable=True))
    op.add_column("notes", sa.Column("search_tokens_ai_summary", sa.Text(), nullable=True))

    op.add_column("note_blocks", sa.Column("search_tokens_text", sa.Text(), nullable=True))

    op.drop_index("ix_notes_search_tsv_gin", table_name="notes")
    op.drop_column("notes", "search_tsv")
    op.add_column(
        "notes",
        sa.Column("search_tsv", postgresql.TSVECTOR(), sa.Computed(NOTES_TSV, persisted=True)),
    )
    op.create_index("ix_notes_search_tsv_gin", "notes", ["search_tsv"], postgresql_using="gin")

    op.drop_index("ix_note_blocks_search_tsv_gin", table_name="note_blocks")
    op.drop_column("note_blocks", "search_tsv")
    op.add_column(
        "note_blocks",
        sa.Column("search_tsv", postgresql.TSVECTOR(), sa.Computed(BLOCKS_TSV, persisted=True)),
    )
    op.create_index(
        "ix_note_blocks_search_tsv_gin", "note_blocks", ["search_tsv"], postgresql_using="gin"
    )

    # --- embeddings --------------------------------------------------------
    op.create_table(
        "embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_type", sa.String(length=8), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("owner_type IN ('note', 'block')", name="embeddings_owner_type_valid"),
        sa.CheckConstraint("dim > 0", name="embeddings_dim_positive"),
        sa.CheckConstraint("chunk_index >= 0", name="embeddings_chunk_index_non_negative"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type", "owner_id", "chunk_index", "model", name="embeddings_owner_chunk_model_unique"
        ),
    )
    # Declared as text above so the DDL does not pin a dimension; converted to
    # the real pgvector type here.
    op.execute(
        f"ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector USING embedding::vector"
    )

    op.create_index("ix_embeddings_household_owner", "embeddings", ["household_id", "owner_type", "owner_id"])
    op.create_index("ix_embeddings_active", "embeddings", ["household_id", "is_active"], postgresql_where=sa.text("is_active"))
    op.create_index("ix_embeddings_content_hash", "embeddings", ["content_hash"])

    # Partial expression index: pgvector rejects a dimension-less column
    # ("column does not have dimensions") but accepts the cast. The predicate
    # must match the query's own WHERE clause for the planner to use it.
    op.execute(
        f"CREATE INDEX ix_embeddings_hnsw ON embeddings "
        f"USING hnsw ((embedding::vector({DEFAULT_DIM})) vector_cosine_ops) "
        f"WITH (m = 16, ef_construction = 64) "
        f"WHERE dim = {DEFAULT_DIM} AND is_active"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_hnsw")
    op.drop_index("ix_embeddings_content_hash", table_name="embeddings")
    op.drop_index("ix_embeddings_active", table_name="embeddings")
    op.drop_index("ix_embeddings_household_owner", table_name="embeddings")
    op.drop_table("embeddings")

    op.drop_index("ix_note_blocks_search_tsv_gin", table_name="note_blocks")
    op.drop_column("note_blocks", "search_tsv")
    op.add_column(
        "note_blocks",
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(text_content, '') || ' ' || "
                "coalesce(caption, '') || ' ' || coalesce(ai_description, '') || ' ' || "
                "coalesce(ocr_text, '') || ' ' || coalesce(transcript, ''))",
                persisted=True,
            ),
        ),
    )
    op.create_index(
        "ix_note_blocks_search_tsv_gin", "note_blocks", ["search_tsv"], postgresql_using="gin"
    )
    op.drop_column("note_blocks", "search_tokens_text")

    op.drop_index("ix_notes_search_tsv_gin", table_name="notes")
    op.drop_column("notes", "search_tsv")
    op.add_column(
        "notes",
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(ai_summary, '')), 'C')",
                persisted=True,
            ),
        ),
    )
    op.create_index("ix_notes_search_tsv_gin", "notes", ["search_tsv"], postgresql_using="gin")
    op.drop_column("notes", "search_tokens_ai_summary")
    op.drop_column("notes", "search_tokens_summary")
    op.drop_column("notes", "search_tokens_title")
