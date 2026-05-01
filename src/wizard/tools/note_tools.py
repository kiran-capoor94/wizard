import logging

from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError

from ..database import get_session
from ..deps import get_note_repo, get_task_repo, get_task_state_repo
from ..mcp_instance import mcp
from ..repositories import NoteRepository, TaskRepository, TaskStateRepository
from ..schemas import (
    MissingResponse,
    RewindResponse,
    RewindSummary,
    Signal,
    TaskContext,
    TimelineEntry,
)

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


async def rewind_task(
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
) -> RewindResponse:
    """Reconstruct the full note timeline for a task, oldest first."""
    logger.info("rewind_task task_id=%d", task_id)
    with get_session() as db:
        try:
            task = t_repo.get_by_id(db, task_id)
        except ValueError as e:
            raise ToolError(str(e)) from e

        task_state = t_state_repo.get_by_task_id(db, task_id)
        if task_state is None:
            raise ToolError(f"TaskState missing for task {task_id}")
        notes_desc = n_repo.get_for_task(db, task_id=task.id)
        notes_asc = [n for n in reversed(notes_desc) if n.id is not None]

        timeline = [
            TimelineEntry(
                note_id=n.id,  # type: ignore[arg-type]  # SQLModel id is Optional; filtered above
                created_at=n.created_at,
                note_type=n.note_type,
                preview=n.content[:200],
                mental_model=n.mental_model,
            )
            for n in notes_asc
        ]

        total_notes = len(notes_asc)
        if total_notes >= 2:
            duration_days = (notes_asc[-1].created_at - notes_asc[0].created_at).days
        else:
            duration_days = 0
        last_activity = notes_asc[-1].created_at if notes_asc else task.created_at

        summary = RewindSummary(
            total_notes=total_notes, duration_days=duration_days, last_activity=last_activity
        )
        return RewindResponse(
            task=TaskContext.from_model(task, task_state), timeline=timeline, summary=summary
        )


async def what_am_i_missing(
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
) -> MissingResponse:
    """Surface cognitive gaps for a task using seven diagnostic rules."""
    logger.info("what_am_i_missing task_id=%d", task_id)
    with get_session() as db:
        try:
            t_repo.get_by_id(db, task_id)
        except ValueError as e:
            raise ToolError(str(e)) from e
        task_state = t_state_repo.get_by_task_id(db, task_id)
        if task_state is None:
            raise ToolError(f"TaskState missing for task {task_id}")

        signals: list[Signal] = []
        nc = task_state.note_count
        dc = task_state.decision_count
        sd = task_state.stale_days

        # Rule 1: no notes at all
        if nc == 0:
            signals.append(
                Signal(
                    type="no_context",
                    severity="high",
                    message="No notes recorded for this task",
                )
            )
        # Rule 2: stale
        if sd >= 3:
            signals.append(
                Signal(
                    type="stale",
                    severity="medium",
                    message=f"No activity for {sd} days",
                )
            )
        # Rule 3: very few notes
        if 0 < nc <= 2:
            signals.append(
                Signal(
                    type="low_context",
                    severity="medium",
                    message="Very few notes — context may be shallow",
                )
            )
        # Rule 4: notes exist but no decisions
        if dc == 0 and nc > 0:
            signals.append(
                Signal(
                    type="no_decisions",
                    severity="medium",
                    message="No decisions recorded",
                )
            )
        # Rule 5: many investigations, no decisions
        if n_repo.count_investigations(db, task_id) > 3 and dc == 0:
            signals.append(
                Signal(
                    type="analysis_loop",
                    severity="high",
                    message="Multiple investigations without a decision",
                )
            )
        # Rule 6: has notes and stale 2-3 days (rule 2 covers >= 3 days; avoid double-signal)
        if task_state.last_note_at is not None and 2 <= sd < 3:
            signals.append(
                Signal(
                    type="lost_context",
                    severity="medium",
                    message="Context may be degrading due to inactivity",
                )
            )
        # Rule 7: no mental model captured
        if nc >= 2 and not n_repo.has_mental_model(db, task_id):
            signals.append(
                Signal(
                    type="no_model",
                    severity="medium",
                    message="No mental model captured — understanding may be shallow",
                )
            )

        signals.sort(key=lambda s: SEVERITY_ORDER[s.severity])
        return MissingResponse(signals=signals)


mcp.tool()(rewind_task)
mcp.tool()(what_am_i_missing)
