"""Indexes for calendar event time-window queries.

The calendar UI asks for events in a window around today. Without an index on
``start_time`` that query scans every row (families accumulate thousands of
events, including recurring ones far in the past). Adds a plain ``start_time``
index plus a composite ``(calendar_id, start_time)`` for per-calendar views.

No data is touched.
"""

from alembic import op

revision = "0012_calendar_event_indexes"
down_revision = "0011_graph_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_calendar_events_start_time",
        "calendar_events",
        ["start_time"],
    )
    op.create_index(
        "ix_calendar_events_calendar_start",
        "calendar_events",
        ["calendar_id", "start_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_events_calendar_start", table_name="calendar_events")
    op.drop_index("ix_calendar_events_start_time", table_name="calendar_events")
