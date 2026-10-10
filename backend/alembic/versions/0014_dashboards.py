"""Dashboards table — user-configurable landing pages.

Creates the ``dashboards`` table. Each dashboard belongs to a household,
stores its widget layout as JSON, and may be set as the household default.
"""

from alembic import op

revision = "0014_dashboards"
down_revision = "0013_calendar_display_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            description TEXT,
            layout VARCHAR(20) NOT NULL DEFAULT 'grid',
            is_default BOOLEAN NOT NULL DEFAULT false,
            widgets JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dashboards_household_id ON dashboards (household_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboards")
