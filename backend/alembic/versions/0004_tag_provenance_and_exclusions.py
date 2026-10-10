"""Add tag provenance, governance metadata, and exclusion memory."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_tag_provenance_and_exclusions"
down_revision = "0003_family_member_pin_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("note_tags", sa.Column("source", sa.String(length=16), server_default="human", nullable=False))
    op.add_column("note_tags", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("note_tags", sa.Column("model", sa.String(length=120), nullable=True))
    op.add_column("note_tags", sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("note_tags", sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("note_tags", sa.Column("applied_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("note_tags", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("note_tags", sa.Column("approved_by_human", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.create_check_constraint("note_tags_source_valid", "note_tags", "source IN ('human','ai','system','imported')")
    op.create_foreign_key("fk_note_tags_applied_by_family_members", "note_tags", "family_members", ["applied_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_note_tags_note_ai", "note_tags", ["note_id"], postgresql_where=sa.text("source = 'ai'"))
    op.create_index("ix_note_tags_tag_source", "note_tags", ["tag_id", "source"])

    op.add_column("tags", sa.Column("namespace", sa.String(length=32), nullable=True))
    op.add_column("tags", sa.Column("canonical_slug", sa.String(length=120), nullable=True))
    op.add_column("tags", sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("tags", sa.Column("ai_usage_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("tags", sa.Column("proposed", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("tags", sa.Column("proposed_by", sa.String(length=16), nullable=True))
    op.add_column("tags", sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("tags", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tags", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tags SET kind = 'topic' WHERE kind = 'general'")
    op.alter_column("tags", "kind", server_default="topic")
    op.create_check_constraint("tags_kind_valid", "tags", "kind IN ('system','facet','topic','adhoc')")
    op.create_index("ix_tags_household_kind_retired", "tags", ["household_id", "kind", "retired_at"])

    op.create_table(
        "tag_exclusions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tag_slug", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=16), server_default="note", nullable=False),
        sa.Column("scope_ref", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_note_type", sa.String(length=40), nullable=True),
        sa.Column("reason", sa.String(length=32), server_default="user_removed", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('note','note_type','member','household')", name="scope_valid"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["family_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_exclusions_household_slug", "tag_exclusions", ["household_id", "tag_slug"])
    op.create_index("ix_tag_exclusions_household_scope_ref", "tag_exclusions", ["household_id", "scope", "scope_ref"])

    op.create_table(
        "tag_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposed_slug", sa.String(length=120), nullable=False),
        sa.Column("proposed_kind", sa.String(length=32), server_default="topic", nullable=False),
        sa.Column("proposed_namespace", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','accepted','rejected','expired','auto_applied')", name="status_valid"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["family_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_proposals_household_status_created", "tag_proposals", ["household_id", "status", "created_at"])

    op.create_table(
        "tag_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tag_slug", sa.String(length=120), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_audit_log_household_created", "tag_audit_log", ["household_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tag_audit_log_household_created", table_name="tag_audit_log")
    op.drop_table("tag_audit_log")
    op.drop_index("ix_tag_proposals_household_status_created", table_name="tag_proposals")
    op.drop_table("tag_proposals")
    op.drop_index("ix_tag_exclusions_household_scope_ref", table_name="tag_exclusions")
    op.drop_index("ix_tag_exclusions_household_slug", table_name="tag_exclusions")
    op.drop_table("tag_exclusions")
    op.drop_index("ix_tags_household_kind_retired", table_name="tags")
    op.drop_constraint("tags_kind_valid", "tags", type_="check")
    for column in ("retired_at", "last_used_at", "first_seen_at", "proposed_by", "proposed", "ai_usage_count", "usage_count", "canonical_slug", "namespace"):
        op.drop_column("tags", column)
    op.drop_index("ix_note_tags_tag_source", table_name="note_tags")
    op.drop_index("ix_note_tags_note_ai", table_name="note_tags")
    op.drop_constraint("fk_note_tags_applied_by_family_members", "note_tags", type_="foreignkey")
    op.drop_constraint("note_tags_source_valid", "note_tags", type_="check")
    for column in ("approved_by_human", "last_verified_at", "applied_by", "applied_at", "evidence", "model", "confidence", "source"):
        op.drop_column("note_tags", column)