"""Helper functions for task tools."""

import logging

from fastmcp.exceptions import ToolError

from ..models import Task, TaskPriority, TaskStatus
from ..security import SecurityService

logger = logging.getLogger(__name__)


def apply_task_fields(
    task: Task,
    sec: SecurityService,
    *,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    due_date: str | None,
    name: str | None,
    source_url: str | None,
) -> list[str]:
    """Apply non-None field values to a Task model. Returns list of updated field names."""
    import datetime

    updated: list[str] = []
    if status is not None:
        task.status = status
        updated.append("status")
    if priority is not None:
        task.priority = priority
        updated.append("priority")
    if due_date is not None:
        try:
            due_date_dt = datetime.datetime.fromisoformat(
                due_date.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ToolError(
                f"Invalid due_date format: {due_date}. Use ISO 8601."
            ) from exc
        task.due_date = due_date_dt
        updated.append("due_date")
    if name is not None:
        task.name = sec.scrub(name).clean
        updated.append("name")
    if source_url is not None:
        task.source_url = source_url
        updated.append("source_url")
    return updated

def task_contexts_to_json(tasks: list) -> str:
    """Serialise a list of TaskContext objects to JSON string.

    Replaces TOON encoding in session_start responses (Wizard v3 Phase 4).
    """
    import json
    return json.dumps([
        {
            "id": t.id,
            "name": t.name,
            "status": t.status.value,
            "priority": t.priority.value,
            "category": t.category.value,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "stale_days": t.stale_days,
            "note_count": t.note_count,
            "decision_count": t.decision_count,
            "last_note_type": t.last_note_type.value if t.last_note_type else None,
            "last_note_preview": t.last_note_preview,
            "source_url": t.source_url,
        }
        for t in tasks
    ])
