"""GraphMemoryService — maps Wizard entities to Graphiti episodes and
orchestrates Graphiti-primary / SQLite-fallback search."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_VALID_TYPES = {"note", "session", "meeting", "task"}


def episode_uuid(entity_type: str, entity_id: int) -> str:
    return f"wizard-{entity_type}-{entity_id}"


def parse_episode_uuid(uuid: str) -> tuple[str, int] | None:
    parts = uuid.split("-", 2)
    if len(parts) != 3 or parts[0] != "wizard" or parts[1] not in _VALID_TYPES:
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


def note_body(
    note_type: str, content: str, mental_model: str | None,
    task_id: int | None, session_id: int | None, supersedes_note_id: int | None,
) -> str:
    return json.dumps({
        "kind": "note", "id": None, "note_type": note_type, "content": content,
        "mental_model": mental_model, "task_id": task_id, "session_id": session_id,
        "supersedes": episode_uuid("note", supersedes_note_id) if supersedes_note_id else None,
    })


def session_body(
    intent: str, state_delta: str, open_loops: list[str],
    next_actions: list[str], closure_status: str,
) -> str:
    return json.dumps({
        "kind": "session", "intent": intent, "state_delta": state_delta,
        "open_loops": open_loops, "next_actions": next_actions,
        "closure_status": closure_status,
    })


def meeting_body(title: str, category: str, content: str, summary: str | None) -> str:
    return json.dumps({
        "kind": "meeting", "title": title, "category": category,
        "content": content, "summary": summary,
    })
