"""vacuum_and_fts_rebuild

Revision ID: vacuum_fts_rebuild
Revises: a2b3c4d5e6f7
Create Date: 2026-05-02

One-time maintenance: set auto_vacuum=INCREMENTAL, VACUUM the database to
reclaim FTS5 tombstone bloat, then rebuild all four FTS indexes.
auto_vacuum must be set before VACUUM so the mode is persisted in the DB header.
"""

from alembic import op
import sqlalchemy as sa

revision = "vacuum_fts_rebuild"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("PRAGMA auto_vacuum=INCREMENTAL"))
    conn.execute(sa.text("VACUUM"))
    conn.execute(sa.text("INSERT INTO note_fts(note_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO task_fts(task_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO session_fts(session_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO meeting_fts(meeting_fts) VALUES('rebuild')"))


def downgrade() -> None:
    pass  # VACUUM cannot be undone; auto_vacuum mode change is harmless
