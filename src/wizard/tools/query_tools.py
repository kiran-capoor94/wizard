"""Read-only query tools. No side effects. No session required."""

import base64
import contextlib
import json
import logging

from fastmcp.dependencies import Depends
from sqlmodel import Session

from ..database import get_session
from ..deps import get_note_repo, get_session_repo, get_task_repo, get_task_state_repo
from ..mcp_instance import mcp
from ..repositories import NoteRepository, SessionRepository, TaskRepository, TaskStateRepository
from ..schemas import (
    GetSessionsResponse,
    GetTasksResponse,
    NoteDetail,
    SessionDetailResponse,
    SessionState,
    SessionSummary,
    TaskDetailResponse,
    TaskSummary,
)

logger = logging.getLogger(__name__)


def _encode_cursor(offset: int) -> str:
    return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()


def _decode_cursor(cursor: str) -> int:
    try:
        offset = json.loads(base64.b64decode(cursor).decode()).get("offset", 0)
        return int(offset) if offset is not None else 0
    except Exception:
        return 0


async def get_tasks(
    status: list[str] | None = None,
    source_type: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    ts_repo: TaskStateRepository = Depends(get_task_state_repo),
    db: Session = Depends(get_session),
) -> GetTasksResponse:
    """List tasks with optional status and source_type filters. Paginated."""
    offset = _decode_cursor(cursor) if cursor else 0
    tasks = t_repo.list_paginated(
        db, status_filter=status, source_type_filter=source_type,
        limit=limit + 1, offset=offset,
    )
    has_more = len(tasks) > limit
    items = tasks[:limit]

    state_map = {
        ts.task_id: ts
        for ts in ts_repo.get_for_tasks(db, [t.id for t in items if t.id])
    }

    summaries = [
        TaskSummary(
            id=t.id,
            name=t.name,
            status=t.status.value,
            priority=t.priority.value,
            category=t.category.value,
            source_id=t.source_id,
            source_type=t.source_type,
            source_url=t.source_url,
            stale_days=state_map[t.id].stale_days if t.id in state_map else 0,
            note_count=state_map[t.id].note_count if t.id in state_map else 0,
            due_date=t.due_date,
            last_worked_at=state_map[t.id].last_note_at if t.id in state_map else None,
        )
        for t in items
    ]

    return GetTasksResponse(
        items=summaries,
        next_cursor=_encode_cursor(offset + limit) if has_more else None,
        total_returned=len(summaries),
    )


async def get_task(
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    db: Session = Depends(get_session),
) -> TaskDetailResponse:
    """Get a single task with all its notes. Read-only — does not log access."""
    task = t_repo.get(db, task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")

    notes_raw = n_repo.list_for_task(db, task_id)
    notes = [
        NoteDetail(
            id=n.id,
            note_type=n.note_type.value,
            content=n.content,
            mental_model=n.mental_model,
            created_at=n.created_at,
        )
        for n in notes_raw
    ]

    latest_mental_model = next(
        (n.mental_model for n in reversed(notes_raw) if n.mental_model), None
    )

    summary = TaskSummary(
        id=task.id, name=task.name, status=task.status.value,
        priority=task.priority.value, category=task.category.value,
        source_id=task.source_id, source_type=task.source_type,
        source_url=task.source_url, due_date=task.due_date,
    )

    return TaskDetailResponse(task=summary, notes=notes, latest_mental_model=latest_mental_model)


async def get_sessions(
    closure_status: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
    s_repo: SessionRepository = Depends(get_session_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    db: Session = Depends(get_session),
) -> GetSessionsResponse:
    """List sessions, newest first. Paginated."""
    offset = _decode_cursor(cursor) if cursor else 0
    sessions = s_repo.list_paginated(
        db, closure_status_filter=closure_status, limit=limit + 1, offset=offset,
    )
    has_more = len(sessions) > limit
    items = sessions[:limit]

    summaries = []
    for s in items:
        note_count = n_repo.count_for_session(db, s.id)
        intent = None
        if s.session_state:
            with contextlib.suppress(Exception):
                intent = SessionState.model_validate_json(s.session_state).intent
        summaries.append(SessionSummary(
            id=s.id, created_at=s.created_at, updated_at=s.updated_at,
            closure_status=s.closed_by, intent=intent, note_count=note_count,
        ))

    return GetSessionsResponse(
        items=summaries,
        next_cursor=_encode_cursor(offset + limit) if has_more else None,
        total_returned=len(summaries),
    )


async def get_session(
    session_id: int,
    s_repo: SessionRepository = Depends(get_session_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    db: Session = Depends(get_session),
) -> SessionDetailResponse:
    """Get a single session with its notes and state."""
    session = s_repo.get(db, session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")

    state = None
    if session.session_state:
        with contextlib.suppress(Exception):
            state = SessionState.model_validate_json(session.session_state)

    notes_raw = n_repo.list_for_session(db, session_id)
    notes = [
        NoteDetail(
            id=n.id, note_type=n.note_type.value, content=n.content,
            mental_model=n.mental_model, created_at=n.created_at,
        )
        for n in notes_raw
    ]

    note_count = len(notes)
    intent = state.intent if state else None
    summary = SessionSummary(
        id=session.id, created_at=session.created_at, updated_at=session.updated_at,
        closure_status=session.closed_by, intent=intent, note_count=note_count,
    )

    return SessionDetailResponse(session=summary, session_state=state, notes=notes)


mcp.tool()(get_tasks)
mcp.tool()(get_task)
mcp.tool()(get_sessions)
mcp.tool()(get_session)
