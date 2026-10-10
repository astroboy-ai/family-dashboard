"""Dashboard templates and agent-created dashboards.

Creates dashboard_templates for agent-created templates,
and adds agent_id to dashboards so agents can create
dashboards for users.
"""

from alembic import op

revision = "0015_dashboard_templates"
down_revision = "0014_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dashboard templates table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(120) NOT NULL,
            description TEXT,
            layout_type VARCHAR(30) NOT NULL,
            widgets JSONB NOT NULL DEFAULT '[]'::jsonb,
            is_system BOOLEAN NOT NULL DEFAULT false,
            created_by VARCHAR(120),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dashboard_templates_is_system ON dashboard_templates (is_system)"
    )
    # Add agent_id to dashboards (for agent-created dashboards)
    op.execute(
        "ALTER TABLE dashboards ADD COLUMN IF NOT EXISTS agent_id VARCHAR(120)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE dashboards DROP COLUMN IF EXISTS agent_id")
    op.execute("DROP TABLE IF EXISTS dashboard_templates")

