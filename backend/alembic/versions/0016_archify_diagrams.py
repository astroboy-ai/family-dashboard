"""Archify diagrams and their tags.

Creates archify_diagrams (standalone Archify HTML diagrams) and
archify_diagram_tags (junction table to the existing tags table).
"""

from alembic import op

revision = "0016_archify_diagrams"
down_revision = "0015_dashboard_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS archify_diagrams (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            household_id UUID NOT NULL REFERENCES households(id) ON DELETE CASCADE,
            title TEXT,
            type VARCHAR(40),
            html TEXT,
            created_by UUID REFERENCES family_members(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            search_tokens_text TEXT,
            search_tsv TSVECTOR GENERATED ALWAYS AS (
                setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(type, '')), 'B') ||
                to_tsvector('simple', coalesce(search_tokens_text, ''))
            ) STORED
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS archify_diagram_tags (
            diagram_id UUID NOT NULL REFERENCES archify_diagrams(id) ON DELETE CASCADE,
            tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            applied_by UUID REFERENCES family_members(id) ON DELETE SET NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (diagram_id, tag_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_archify_diagrams_household_updated
        ON archify_diagrams (household_id, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_archify_diagrams_search_tsv_gin
        ON archify_diagrams USING gin (search_tsv)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS archify_diagram_tags")
    op.execute("DROP TABLE IF EXISTS archify_diagrams")
