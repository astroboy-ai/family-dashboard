"""Add family-member PIN authentication state."""

from alembic import op
import sqlalchemy as sa


revision = "0003_family_member_pin_auth"
down_revision = "0002_note_block_thumb_media_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("family_members", sa.Column("pin_hash", sa.Text(), nullable=True))
    op.add_column(
        "family_members",
        sa.Column("pin_failed_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "family_members",
        sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("family_members", "pin_locked_until")
    op.drop_column("family_members", "pin_failed_attempts")
    op.drop_column("family_members", "pin_hash")