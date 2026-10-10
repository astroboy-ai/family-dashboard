"""Indexes for calendar event time-window queries.

The calendar UI asks for events in a window around today. Without an index on
``start_time`` that query scans every row (families accumulate thousands of
events, including recurring ones far in the past). Adds a plain ``start_time``
index plus a composite ``(calendar_id, start_time)`` for per-calendar views.

Both are created with ``IF NOT EXISTS``: SQLAlchemy's ``create_all`` may have
already produced the single-column index on an existing deployment, and a
duplicate ``CREATE INDEX`` would abort startup.

No data is touched.
"""

from alembic import op

revision = "0012_calendar_event_indexes"
down_revision = "0011_graph_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_calendar_events_start_time "
        "ON calendar_events (start_time)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_calendar_events_calendar_start "
        "ON calendar_events (calendar_id, start_time)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_calendar_events_calendar_start")
    op.execute("DROP INDEX IF EXISTS ix_calendar_events_start_time")
