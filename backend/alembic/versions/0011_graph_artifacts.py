"""Imported Archify artifacts.

Adds ``graph_artifacts``: one row per imported Archify output file (an
interactive HTML produced outside FamilyOS, or a PNG/SVG/JSON export).

Kept separate from ``graph_views``: a view is a configuration FamilyOS renders
natively, an artifact is opaque content it only displays in a sandboxed iframe.
No existing data is touched.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_graph_artifacts"
down_revision = "0010_calendar_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graph_artifacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="html"),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="manual"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_asset_id"], ["media_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["family_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_graph_artifacts_household_order", "graph_artifacts", ["household_id", "order_index"]
    )
    op.create_index(
        "ix_graph_artifacts_household_created", "graph_artifacts", ["household_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_graph_artifacts_household_created", table_name="graph_artifacts")
    op.drop_index("ix_graph_artifacts_household_order", table_name="graph_artifacts")
    op.drop_table("graph_artifacts")
