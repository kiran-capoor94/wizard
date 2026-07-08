"""vacuum_and_fts_rebuild

Revision ID: vacuum_fts_rebuild
Revises: a2b3c4d5e6f7
Create Date: 2026-05-02

One-time maintenance: set auto_vacuum=INCREMENTAL, VACUUM the database to
reclaim FTS5 tombstone bloat, then rebuild all four FTS indexes.
auto_vacuum must be set before VACUUM so the mode is persisted in the DB header.
"""

import contextlib

from alembic import op
import sqlalchemy as sa

revision = "vacuum_fts_rebuild"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # VACUUM cannot run inside a transaction. Whether one is open here at all
    # is unreliable: env.py shares one transaction across the whole `upgrade`
    # run, but SQLAlchemy's sqlite driver only actually sends "BEGIN" the
    # first time a statement executes on this connection (autobegin) — so
    # depending on which migrations ran before this one in a given upgrade
    # invocation, a transaction may or may not actually be open. Close it if
    # one is open, tolerate it if not, then always reopen so alembic's own
    # commit at the end of this migration has a transaction to work with.
    with contextlib.suppress(sa.exc.OperationalError):
        conn.exec_driver_sql("COMMIT")  # no-op if nothing was open
    try:
        conn.exec_driver_sql("PRAGMA auto_vacuum=INCREMENTAL")
        conn.exec_driver_sql("VACUUM")
    finally:
        conn.exec_driver_sql("BEGIN")
    conn.execute(sa.text("INSERT INTO note_fts(note_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO task_fts(task_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO session_fts(session_fts) VALUES('rebuild')"))
    conn.execute(sa.text("INSERT INTO meeting_fts(meeting_fts) VALUES('rebuild')"))


def downgrade() -> None:
    pass  # VACUUM cannot be undone; auto_vacuum mode change is harmless
