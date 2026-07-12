"""Rebuild FTS5 tables with Porter stemming.

Revision ID: b1c2d3e4f5a6
Revises: restore_fts_triggers
Create Date: 2026-07-12 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "restore_fts_triggers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (fts table, base table, column DDL, rebuild insert columns, select body)
_TABLES = [
    ("note_fts", "note",
     "content, note_type UNINDEXED, content='note', content_rowid='id'"),
    ("session_fts", "wizardsession",
     "summary, content='wizardsession', content_rowid='id'"),
    ("meeting_fts", "meeting",
     "content, title, content='meeting', content_rowid='id'"),
    ("task_fts", "task",
     "name, content='task', content_rowid='id'"),
]
# Trigger recreation is identical to migration a2b3c4d5e6f7; only the CREATE
# VIRTUAL TABLE gains `tokenize`. Triggers survive the DROP TABLE? No — they
# reference the base tables, not the fts tables, so they persist. We leave the
# existing triggers in place and only rebuild the virtual tables.


def _recreate(conn, tokenize_clause: str) -> None:
    for fts, _base, ddl in _TABLES:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {fts}"))
        conn.execute(sa.text(
            f"CREATE VIRTUAL TABLE {fts} USING fts5({ddl}{tokenize_clause})"
        ))
        conn.execute(sa.text(f"INSERT INTO {fts}({fts}) VALUES('rebuild')"))


def upgrade() -> None:
    conn = op.get_bind()
    _recreate(conn, ", tokenize='porter unicode61'")


def downgrade() -> None:
    conn = op.get_bind()
    _recreate(conn, "")
