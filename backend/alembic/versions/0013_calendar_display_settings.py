"""Local calendar display settings: theme and customisation flag.

Adds two columns to ``calendars``:

- ``theme`` — a named light/dark preset chosen per calendar (FamilyOS-side
  display only, never sent to Google).
- ``is_customized`` — set when a member renames or recolours a calendar
  locally. The sync refreshes ``name``/``color`` from Google on every run, so
  without this flag a local rename would be silently undone every 15 minutes.

Existing rows default to ``is_customized = false``, which keeps today's
behaviour (Google owns the name and colour) until a member edits one.

No existing data is modified.
"""

from alembic import op

revision = "0013_calendar_display_settings"
down_revision = "0012_calendar_event_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE calendars ADD COLUMN IF NOT EXISTS theme VARCHAR(32)")
    op.execute(
        "ALTER TABLE calendars ADD COLUMN IF NOT EXISTS is_customized BOOLEAN "
        "NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE calendars DROP COLUMN IF EXISTS is_customized")
    op.execute("ALTER TABLE calendars DROP COLUMN IF EXISTS theme")
