"""Calendar permissions and device views.

Calendar is now an independent object, not bound to a system user.
- CalendarPermission: who can view/edit/manage/admin each calendar
- CalendarView: device/dashboard config (which calendars to show, layout)

Permission levels: view < edit < manage < admin
- view: see events
- edit: create/update/delete events
- manage: edit calendar settings + permissions
- admin: delete calendar + manage household members
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_calendar_permissions"
down_revision = "0009_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CalendarPermission: who can do what with each calendar
    op.create_table(
        "calendar_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("calendar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="view"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["calendar_id"], ["calendars.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_id", "member_id", name="uq_calendar_permissions_calendar_member"),
        sa.CheckConstraint("level IN ('view', 'edit', 'manage', 'admin')", name="ck_calendar_permissions_level"),
    )
    op.create_index("ix_calendar_permissions_calendar_id", "calendar_permissions", ["calendar_id"])
    op.create_index("ix_calendar_permissions_member_id", "calendar_permissions", ["member_id"])

    # CalendarView: device/dashboard configuration
    op.create_table(
        "calendar_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("calendar_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("layout", sa.String(16), nullable=False, server_default="month"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("layout IN ('month', 'week', 'day', 'agenda')", name="ck_calendar_views_layout"),
    )
    op.create_index("ix_calendar_views_household_id", "calendar_views", ["household_id"])

    # Add is_active to calendars
    op.add_column("calendars", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_table("calendar_views")
    op.drop_table("calendar_permissions")
    op.drop_column("calendars", "is_active")
