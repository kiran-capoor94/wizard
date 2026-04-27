"""backfill_artifact_ids

Revision ID: 95ee99a3db06
Revises: f0fb7ac74c46
Create Date: 2026-04-24 00:49:02.896707

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95ee99a3db06'
down_revision: Union[str, Sequence[str], None] = 'f0fb7ac74c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill artifact_id UUIDs for all existing rows."""
    conn = op.get_bind()
    for table in ("task", "wizardsession", "meeting"):
        rows = conn.execute(
            sa.text(f"SELECT id FROM {table} WHERE artifact_id IS NULL")
        ).fetchall()
        for (row_id,) in rows:
            conn.execute(
                sa.text(f"UPDATE {table} SET artifact_id = :aid WHERE id = :id"),
                {"aid": str(uuid.uuid4()), "id": row_id},
            )
    # Backfill note.artifact_id from existing FKs (task takes priority over session over meeting)
    conn.execute(sa.text("""
        UPDATE note SET
            artifact_id = (SELECT artifact_id FROM task WHERE task.id = note.task_id),
            artifact_type = 'task'
        WHERE task_id IS NOT NULL AND artifact_id IS NULL
    """))
    conn.execute(sa.text("""
        UPDATE note SET
            artifact_id = (SELECT artifact_id FROM wizardsession WHERE wizardsession.id = note.session_id),
            artifact_type = 'session'
        WHERE session_id IS NOT NULL AND artifact_id IS NULL AND task_id IS NULL
    """))
    conn.execute(sa.text("""
        UPDATE note SET
            artifact_id = (SELECT artifact_id FROM meeting WHERE meeting.id = note.meeting_id),
            artifact_type = 'meeting'
        WHERE meeting_id IS NOT NULL AND artifact_id IS NULL AND task_id IS NULL AND session_id IS NULL
    """))
    # Backfill synthesis_status for sessions already synthesised before the column existed
    conn.execute(sa.text(
        "UPDATE wizardsession SET synthesis_status = 'complete' WHERE is_synthesised = 1"
    ))


def downgrade() -> None:
    pass  # backfill is safe to leave — columns still exist after downgrade
