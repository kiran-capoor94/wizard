"""Add FTS5 search tables for notes, sessions, meetings, tasks.

Revision ID: a2b3c4d5e6f7
Revises: 75c94727cfc5
Create Date: 2026-05-01 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "75c94727cfc5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # FTS5 virtual tables — content-based (rowid = entity id).
    # Only index columns that exist in the base table; rowid serves as entity ID.
    conn.execute(sa.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5("
        "content, note_type UNINDEXED,"
        "content='note', content_rowid='id'"
        ")"
    ))
    conn.execute(sa.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5("
        "summary,"
        "content='wizardsession', content_rowid='id'"
        ")"
    ))
    conn.execute(sa.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS meeting_fts USING fts5("
        "content, title,"
        "content='meeting', content_rowid='id'"
        ")"
    ))
    conn.execute(sa.text(
        "CREATE VIRTUAL TABLE IF NOT EXISTS task_fts USING fts5("
        "name,"
        "content='task', content_rowid='id'"
        ")"
    ))

    # Triggers to keep note_fts in sync
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS note_fts_ai AFTER INSERT ON note BEGIN "
        "INSERT INTO note_fts(rowid, content, note_type) "
        "VALUES (new.id, new.content, new.note_type); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS note_fts_ad AFTER DELETE ON note BEGIN "
        "INSERT INTO note_fts(note_fts, rowid, content, note_type) "
        "VALUES ('delete', old.id, old.content, old.note_type); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS note_fts_au AFTER UPDATE ON note BEGIN "
        "INSERT INTO note_fts(note_fts, rowid, content, note_type) "
        "VALUES ('delete', old.id, old.content, old.note_type);"
        "INSERT INTO note_fts(rowid, content, note_type) "
        "VALUES (new.id, new.content, new.note_type); END"
    ))

    # Triggers to keep session_fts in sync
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS session_fts_ai AFTER INSERT ON wizardsession BEGIN "
        "INSERT INTO session_fts(rowid, summary) "
        "VALUES (new.id, new.summary); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS session_fts_ad AFTER DELETE ON wizardsession BEGIN "
        "INSERT INTO session_fts(session_fts, rowid, summary) "
        "VALUES ('delete', old.id, old.summary); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS session_fts_au AFTER UPDATE ON wizardsession BEGIN "
        "INSERT INTO session_fts(session_fts, rowid, summary) "
        "VALUES ('delete', old.id, old.summary);"
        "INSERT INTO session_fts(rowid, summary) "
        "VALUES (new.id, new.summary); END"
    ))

    # Triggers to keep meeting_fts in sync
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS meeting_fts_ai AFTER INSERT ON meeting BEGIN "
        "INSERT INTO meeting_fts(rowid, content, title) "
        "VALUES (new.id, new.content, new.title); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS meeting_fts_ad AFTER DELETE ON meeting BEGIN "
        "INSERT INTO meeting_fts(meeting_fts, rowid, content, title) "
        "VALUES ('delete', old.id, old.content, old.title); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS meeting_fts_au AFTER UPDATE ON meeting BEGIN "
        "INSERT INTO meeting_fts(meeting_fts, rowid, content, title) "
        "VALUES ('delete', old.id, old.content, old.title);"
        "INSERT INTO meeting_fts(rowid, content, title) "
        "VALUES (new.id, new.content, new.title); END"
    ))

    # Triggers to keep task_fts in sync
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS task_fts_ai AFTER INSERT ON task BEGIN "
        "INSERT INTO task_fts(rowid, name) "
        "VALUES (new.id, new.name); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS task_fts_ad AFTER DELETE ON task BEGIN "
        "INSERT INTO task_fts(task_fts, rowid, name) "
        "VALUES ('delete', old.id, old.name); END"
    ))
    conn.execute(sa.text(
        "CREATE TRIGGER IF NOT EXISTS task_fts_au AFTER UPDATE ON task BEGIN "
        "INSERT INTO task_fts(task_fts, rowid, name) "
        "VALUES ('delete', old.id, old.name);"
        "INSERT INTO task_fts(rowid, name) "
        "VALUES (new.id, new.name); END"
    ))

    # Backfill existing rows
    conn.execute(sa.text(
        "INSERT INTO note_fts(rowid, content, note_type) "
        "SELECT id, content, note_type FROM note WHERE content IS NOT NULL"
    ))
    conn.execute(sa.text(
        "INSERT INTO session_fts(rowid, summary) "
        "SELECT id, summary FROM wizardsession WHERE summary IS NOT NULL"
    ))
    conn.execute(sa.text(
        "INSERT INTO meeting_fts(rowid, content, title) "
        "SELECT id, content, title FROM meeting WHERE content IS NOT NULL"
    ))
    conn.execute(sa.text(
        "INSERT INTO task_fts(rowid, name) "
        "SELECT id, name FROM task WHERE name IS NOT NULL"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    for trigger in [
        "note_fts_ai", "note_fts_ad", "note_fts_au",
        "session_fts_ai", "session_fts_ad", "session_fts_au",
        "meeting_fts_ai", "meeting_fts_ad", "meeting_fts_au",
        "task_fts_ai", "task_fts_ad", "task_fts_au",
    ]:
        conn.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
    for table in ["note_fts", "session_fts", "meeting_fts", "task_fts"]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
