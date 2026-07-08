"""fix_remaining_note_type_case

Revision ID: 1fd03acf7859
Revises: 9cd1a0c203d0
Create Date: 2026-07-06

9cd1a0c203d0 only fixed note_type='observation' -> 'OBSERVATION'. The original
schema (1bbc6e61da58) created the note_type column with the lowercase set
('investigation', 'decision', 'docs', 'learnings', 'session_summary'); rows
written under that schema still carry the lowercase value and are invisible
to every query that filters on the now-uppercase NoteType enum. 'failure' is
included defensively even though no lowercase 'failure' rows are known to
exist — the UPDATE is a no-op if none match.
"""
from alembic import op
import sqlalchemy as sa

revision = "1fd03acf7859"
down_revision = "9cd1a0c203d0"
branch_labels = None
depends_on = None

_LEGACY_TO_CURRENT = {
    "investigation": "INVESTIGATION",
    "decision": "DECISION",
    "docs": "DOCS",
    "learnings": "LEARNINGS",
    "session_summary": "SESSION_SUMMARY",
    "failure": "FAILURE",
}


def upgrade() -> None:
    conn = op.get_bind()
    for legacy, current in _LEGACY_TO_CURRENT.items():
        conn.execute(
            sa.text("UPDATE note SET note_type = :current WHERE note_type = :legacy"),
            {"current": current, "legacy": legacy},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for legacy, current in _LEGACY_TO_CURRENT.items():
        conn.execute(
            sa.text("UPDATE note SET note_type = :legacy WHERE note_type = :current"),
            {"legacy": legacy, "current": current},
        )
