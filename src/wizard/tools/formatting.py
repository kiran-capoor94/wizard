"""Serialisation helpers and shared notification utilities for MCP tool responses."""

import contextlib
import json
from typing import Any, Coroutine

import anyio

from ..schemas import TaskContext


async def _try_notify(coro: Coroutine[Any, Any, None]) -> None:
    """Run a ctx.info / ctx.report_progress / ctx.debug call, ignoring closed-transport errors."""
    with contextlib.suppress(anyio.ClosedResourceError, anyio.BrokenResourceError):
        await coro


def task_contexts_to_json(tasks: list[TaskContext]) -> str:
    """Serialise a list of TaskContext objects to JSON string.

    Replaces TOON encoding in session_start responses (Wizard v3 Phase 4).
    """
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
