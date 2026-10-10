from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("locale", sa.String(length=16), server_default="en", nullable=False),
        sa.Column("week_starts_on", sa.String(length=16), server_default="monday", nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_households"),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "family_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("full_name", sa.String(length=240), nullable=True),
        sa.Column("avatar_media_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("birthdate", sa.Date(), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("points_cached", sa.Integer(), server_default="0", nullable=False),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('parent', 'child', 'guest', 'device')", name="role_valid"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="fk_family_members_household_id_households", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_family_members_user_id_users", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_family_members"),
        sa.UniqueConstraint("user_id", name="uq_family_members_user_id"),
    )
    op.create_table(
        "device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="fk_device_tokens_household_id_households", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"], name="fk_device_tokens_member_id_family_members", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_device_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_device_tokens_token_hash"),
    )
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=32), server_default="general", nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="fk_tags_household_id_households", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.UniqueConstraint("household_id", "slug", name="uq_tags_household_slug_unique"),
    )
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("thumb_key", sa.String(length=512), nullable=True),
        sa.Column("mime", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enrichment_status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('image', 'audio', 'video', 'file')", name="kind_valid"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="fk_media_assets_household_id_households", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["family_members.id"], name="fk_media_assets_uploaded_by_family_members", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_media_assets"),
        sa.UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
    )
    op.create_foreign_key(
        "fk_family_members_avatar_media_id_media_assets",
        "family_members",
        "media_assets",
        ["avatar_media_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=40), server_default="freeform", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="inbox", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visibility", sa.String(length=16), server_default="family", nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parent_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("embedding_status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(ai_summary, '')), 'C')",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("visibility IN ('family', 'parents', 'private')", name="visibility_valid"),
        sa.ForeignKeyConstraint(["created_by"], ["family_members.id"], name="fk_notes_created_by_family_members", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="fk_notes_household_id_households", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_member_id"], ["family_members.id"], name="fk_notes_owner_member_id_family_members", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_note_id"], ["notes.id"], name="fk_notes_parent_note_id_notes", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_notes"),
    )
    op.create_table(
        "note_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("ai_description", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("importance", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(text_content, '') || ' ' || "
                "coalesce(caption, '') || ' ' || coalesce(ai_description, '') || ' ' || "
                "coalesce(ocr_text, '') || ' ' || coalesce(transcript, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("importance BETWEEN 0 AND 5", name="importance_range"),
        sa.ForeignKeyConstraint(["media_asset_id"], ["media_assets.id"], name="fk_note_blocks_media_asset_id_media_assets", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], name="fk_note_blocks_note_id_notes", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_note_blocks"),
        sa.UniqueConstraint("note_id", "order_index", name="uq_note_blocks_note_order_unique"),
    )
    op.create_table(
        "note_tags",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], name="fk_note_tags_note_id_notes", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], name="fk_note_tags_tag_id_tags", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("note_id", "tag_id", name="pk_note_tags"),
    )
    op.create_table(
        "note_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("from_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["from_note_id"], ["notes.id"], name="fk_note_relations_from_note_id_notes", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_note_id"], ["notes.id"], name="fk_note_relations_to_note_id_notes", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_note_relations"),
        sa.UniqueConstraint("from_note_id", "to_note_id", "relation_type", name="uq_note_relations_note_relation_unique"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("ref_type", sa.String(length=40), nullable=True),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.SmallInteger(), server_default="2", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel", sa.String(length=24), server_default="inapp", nullable=False),
        sa.Column("dedupe_key", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="fk_notifications_household_id_households", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"], name="fk_notifications_member_id_family_members", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.UniqueConstraint("household_id", "dedupe_key", name="uq_notifications_household_dedupe_unique"),
    )
    op.create_table(
        "tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("icon", sa.String(length=80), nullable=True),
        sa.Column("route", sa.String(length=240), nullable=True),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.String(length=40), server_default="1", nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tools"),
        sa.UniqueConstraint("slug", name="uq_tools_slug"),
    )
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent", sa.String(length=80), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_agent_tool_calls"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_table(
        "jobs_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_jobs_outbox"),
    )

    op.create_index("ix_media_assets_household_sha256", "media_assets", ["household_id", "sha256"])
    op.create_index(
        "ix_media_assets_enrichment_incomplete",
        "media_assets",
        ["enrichment_status"],
        postgresql_where=sa.text("enrichment_status <> 'complete'"),
    )
    op.create_index(
        "ix_notes_household_status_updated",
        "notes",
        ["household_id", "status", sa.text("updated_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_notes_household_expires",
        "notes",
        ["household_id", "expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index("ix_notes_extra_gin", "notes", ["extra"], postgresql_using="gin", postgresql_ops={"extra": "jsonb_path_ops"})
    op.create_index("ix_notes_search_tsv_gin", "notes", ["search_tsv"], postgresql_using="gin")
    op.create_index("ix_note_blocks_search_tsv_gin", "note_blocks", ["search_tsv"], postgresql_using="gin")
    op.create_index(
        "ix_note_blocks_expires",
        "note_blocks",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index("ix_notifications_inbox", "notifications", ["household_id", "member_id", "read_at", "scheduled_for"])
    op.create_index("ix_agent_tool_calls_household_created", "agent_tool_calls", ["household_id", "created_at"])
    op.create_index("ix_audit_log_household_created", "audit_log", ["household_id", "created_at"])
    op.create_index("ix_jobs_outbox_available", "jobs_outbox", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_outbox_available", table_name="jobs_outbox")
    op.drop_index("ix_audit_log_household_created", table_name="audit_log")
    op.drop_index("ix_agent_tool_calls_household_created", table_name="agent_tool_calls")
    op.drop_index("ix_notifications_inbox", table_name="notifications")
    op.drop_index("ix_note_blocks_expires", table_name="note_blocks")
    op.drop_index("ix_note_blocks_search_tsv_gin", table_name="note_blocks")
    op.drop_index("ix_notes_search_tsv_gin", table_name="notes")
    op.drop_index("ix_notes_extra_gin", table_name="notes")
    op.drop_index("ix_notes_household_expires", table_name="notes")
    op.drop_index("ix_notes_household_status_updated", table_name="notes")
    op.drop_index("ix_media_assets_enrichment_incomplete", table_name="media_assets")
    op.drop_index("ix_media_assets_household_sha256", table_name="media_assets")
    op.drop_constraint("fk_family_members_avatar_media_id_media_assets", "family_members", type_="foreignkey")
    op.drop_table("jobs_outbox")
    op.drop_table("audit_log")
    op.drop_table("agent_tool_calls")
    op.drop_table("tools")
    op.drop_table("notifications")
    op.drop_table("note_relations")
    op.drop_table("note_tags")
    op.drop_table("note_blocks")
    op.drop_table("notes")
    op.drop_table("media_assets")
    op.drop_table("device_tokens")
    op.drop_table("tags")
    op.drop_table("family_members")
    op.drop_table("users")
    op.drop_table("households")