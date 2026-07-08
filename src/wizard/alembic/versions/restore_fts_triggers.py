"""restore_note_session_fts_triggers

Revision ID: restore_fts_triggers
Revises: 69d7ea262b9b
Create Date: 2026-07-09

`drop_synthesis_columns` ran `batch_alter_table` on `note` and `wizardsession`
to drop columns SQLite can't drop in place — which recreates both tables under
the hood (create new, copy rows, drop old, rename) and silently destroys any
trigger defined on them. That took out `note_fts_ai/ad/au` and
`session_fts_ai/ad/au`, the triggers keeping the FTS5 search index in sync,
while `meeting` and `task` (never batch-altered) kept theirs. Net effect:
`search()` has been silently returning zero results for note and session
content since that migration ran — `note_fts`/`session_fts` stopped being
updated on new inserts, though existing indexed rows kept working.

This recreates the six missing triggers (idempotent — CREATE TRIGGER IF NOT
EXISTS, so a no-op on databases where they somehow still exist) and rebuilds
both FTS indexes from the current table contents to backfill everything
written since they broke.
"""
from alembic import op
import sqlalchemy as sa

revision = "restore_fts_triggers"
down_revision = "69d7ea262b9b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

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

    # Rebuild from current table contents — backfills every note/session
    # written while the triggers were missing.
    conn.execute(sa.text("INSERT INTO note_fts(note_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO session_fts(session_fts) VALUES('rebuild')"))


def downgrade() -> None:
    conn = op.get_bind()
    for trigger in ["note_fts_ai", "note_fts_ad", "note_fts_au",
                     "session_fts_ai", "session_fts_ad", "session_fts_au"]:
        conn.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
