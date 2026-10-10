"""Calendar tables: accounts, calendars, events.

Google Calendar integration requires three tables:
- calendar_accounts: OAuth tokens per family member
- calendars: Google Calendar metadata (sync token for incremental sync)
- calendar_events: cached events with Google event ID for deduplication

All tables cascade on account/calendar deletion. Events are cached locally
so the UI can render without hitting Google API on every page load.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_calendar"
down_revision = "0008_member_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_accounts_household_id", "calendar_accounts", ["household_id"])
    op.create_index("ix_calendar_accounts_member_id", "calendar_accounts", ["member_id"])

    op.create_table(
        "calendars",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_calendar_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sync_token", sa.String(255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["calendar_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "google_calendar_id", name="uq_calendars_account_google"),
    )
    op.create_index("ix_calendars_account_id", "calendars", ["account_id"])

    op.create_table(
        "calendar_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("google_event_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("all_day", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("recurrence", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("attendees", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(32), server_default="confirmed", nullable=False),
        sa.Column("visibility", sa.String(32), nullable=True),
        sa.Column("transparency", sa.String(32), nullable=True),
        sa.Column("ical_uid", sa.String(255), nullable=True),
        sa.Column("html_link", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["calendar_id"], ["calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_id", "google_event_id", name="uq_calendar_events_calendar_google"),
    )
    op.create_index("ix_calendar_events_calendar_id", "calendar_events", ["calendar_id"])
    op.create_index("ix_calendar_events_start_time", "calendar_events", ["start_time"])


def downgrade() -> None:
    op.drop_table("calendar_events")
    op.drop_table("calendars")
    op.drop_table("calendar_accounts")
