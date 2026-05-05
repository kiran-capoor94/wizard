"""drop synthesis columns

Revision ID: drop_synthesis_columns
Revises: vacuum_fts_rebuild
Create Date: 2026-05-05

Remove synthesis-related columns now that the synthesis flow has been
replaced by the Stop hook observation pipeline.
"""

import sqlalchemy as sa
from alembic import op

revision = "drop_synthesis_columns"
down_revision = "b8908e3438a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("wizardsession") as batch_op:
        batch_op.drop_column("transcript_path")
        batch_op.drop_column("is_synthesised")
        batch_op.drop_column("synthesis_status")
        batch_op.drop_column("transcript_raw")

    with op.batch_alter_table("note") as batch_op:
        batch_op.drop_index("ix_note_synthesis_content_hash")
        batch_op.drop_column("synthesis_content_hash")
        batch_op.drop_column("synthesis_session_id")
        batch_op.drop_column("transcript_offset_start")
        batch_op.drop_column("transcript_offset_end")
        batch_op.drop_column("synthesis_confidence")
        batch_op.drop_column("source_note_ids")
        batch_op.add_column(sa.Column("content_hash", sa.String(), nullable=True))
        batch_op.create_index("ix_note_content_hash", ["content_hash"])


def downgrade() -> None:
    pass
