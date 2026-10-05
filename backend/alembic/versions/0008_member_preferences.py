"""Per-member preferences.

Adds ``family_members.preferences`` (JSONB) so per-user display settings can live
with the member rather than the household. The first consumer is the calendar
theme, which is deliberately independent of the system theme.

Existing rows default to an empty object, so nothing changes for current users.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_member_preferences"
down_revision = "0007_graph_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "family_members",
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("family_members", "preferences")
