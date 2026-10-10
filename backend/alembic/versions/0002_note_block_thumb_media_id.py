from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_note_block_thumb_media_id"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "note_blocks",
        sa.Column(
            "thumb_media_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_note_blocks_thumb_media_id_media_assets",
        "note_blocks",
        "media_assets",
        ["thumb_media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_note_blocks_thumb_media_id_media_assets", "note_blocks", type_="foreignkey")
    op.drop_column("note_blocks", "thumb_media_id")
