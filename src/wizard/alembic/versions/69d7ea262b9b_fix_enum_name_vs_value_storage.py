"""fix_enum_name_vs_value_storage

Revision ID: 69d7ea262b9b
Revises: 293db56f33cb
Create Date: 2026-07-07

Before models.py started using an explicit values_callable, SQLAlchemy's
default Enum column bound/read task.status, task.priority, task.category,
meeting.category, and note.status by member NAME (e.g. "MEDIUM"), not by
.value (e.g. "medium") — silently mismatching every lowercase-value filter
in the codebase and the lowercase CHECK-constraint-era migrations. Any row
written through the ORM before this fix may carry an uppercase-name value.
Defensive no-op if none exist.
"""
from alembic import op
import sqlalchemy as sa

revision = "69d7ea262b9b"
down_revision = "293db56f33cb"
branch_labels = None
depends_on = None

_TASK_STATUS = ["todo", "in_progress", "blocked", "done", "archived"]
_TASK_PRIORITY = ["low", "medium", "high"]
_TASK_CATEGORY = ["issue", "bug", "investigation"]
_MEETING_CATEGORY = ["standup", "planning", "retro", "one_on_one", "general"]
_NOTE_STATUS = ["active", "superseded", "contradicted", "archived", "invalid", "unclassified"]


def _normalize(conn, table: str, column: str, values: list[str]) -> None:
    for value in values:
        conn.execute(
            sa.text(f"UPDATE {table} SET {column} = :v WHERE {column} = :name"),  # noqa: S608
            {"v": value, "name": value.upper()},
        )


def upgrade() -> None:
    conn = op.get_bind()
    _normalize(conn, "task", "status", _TASK_STATUS)
    _normalize(conn, "task", "priority", _TASK_PRIORITY)
    _normalize(conn, "task", "category", _TASK_CATEGORY)
    _normalize(conn, "meeting", "category", _MEETING_CATEGORY)
    _normalize(conn, "note", "status", _NOTE_STATUS)


def downgrade() -> None:
    pass  # normalization to the correct casing is not meaningfully reversible
