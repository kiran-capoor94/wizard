"""Session helper functions extracted from session_tools.py to keep it under 500 lines.

Contains: wizard_context builder, prior-summaries builder, previous-session lookup,
resume-session state deserialisation, and prior-notes grouping.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError
from sqlmodel import Session

from ..config import settings
from ..database import get_session
from ..models import WizardSession
from ..repositories import NoteRepository, SessionRepository, TaskRepository
from ..schemas import NoteDetail, PriorSessionSummary, ResumedTaskNotes, SessionState, TaskContext

logger = logging.getLogger(__name__)


def build_wizard_context() -> dict | None:
    ks = settings.knowledge_store
    if ks.type == "notion":
        return {
            "knowledge_store_type": "notion",
            "tasks_db_id": ks.notion.tasks_db_id or None,
            "meetings_db_id": ks.notion.meetings_db_id or None,
            "daily_parent_id": ks.notion.daily_parent_id or None,
        }
    if ks.type == "obsidian":
        return {
            "knowledge_store_type": "obsidian",
            "vault_path": ks.obsidian.vault_path or None,
            "daily_notes_folder": ks.obsidian.daily_notes_folder,
            "tasks_folder": ks.obsidian.tasks_folder,
        }
    return None


def build_prior_summaries(
    db: Session, current_session_id: int
) -> list[PriorSessionSummary]:
    """Return the 3 most recent closed sessions with summaries for prior-context surfacing."""
    summaries = SessionRepository().get_prior_summaries(db, current_session_id)
    result = []
    for s in summaries:
        task_ids: list[int] = []
        if s.raw_session_state:
            try:
                state_obj = SessionState.model_validate_json(s.raw_session_state)
                task_ids = state_obj.working_set
            except (ValueError, ValidationError) as e:
                logger.warning(
                    "build_prior_summaries: corrupt session_state sid=%s: %s",
                    s.session_id, e,
                )
        result.append(s.model_copy(update={"task_ids": task_ids}))
    return result


def find_previous_session_id() -> int | None:
    """Return the most recently created WizardSession id, or None if none exists."""
    with get_session() as db:
        return SessionRepository().get_most_recent_id(db)


def deserialise_session_state(
    db: Session, prior: WizardSession, t_repo: TaskRepository
) -> tuple[SessionState | None, list[TaskContext]]:
    """Deserialise prior session_state JSON and rebuild working set task contexts."""
    if prior.session_state is None:
        logger.warning(
            "Session %d was not cleanly closed — no structured state available. "
            "Falling back to note history.",
            prior.id,
        )
        return None, []
    try:
        state = SessionState.model_validate_json(prior.session_state)
        working_set = t_repo.get_task_contexts_by_ids(db, list(state.working_set))
        return state, working_set
    except (ValueError, ValidationError) as e:
        logger.warning("Failed to deserialise session_state: %s", e)
        return None, []


_RESUME_NOTES_PER_TASK = 3


def group_prior_notes(
    db: Session, session_id: int, n_repo: NoteRepository, t_repo: TaskRepository
) -> list[ResumedTaskNotes]:
    """Query notes for a session, grouped by task with latest mental model.

    Returns at most 3 notes per task (most recent). Full history is available
    via rewind_task when needed.
    """
    by_task = n_repo.get_notes_grouped_by_task(db, session_id, active_only=True)
    if not by_task:
        return []

    task_ids = list(by_task.keys())
    task_contexts = {tc.id: tc for tc in t_repo.get_task_contexts_by_ids(db, task_ids)}

    result: list[ResumedTaskNotes] = []
    for tid, notes in by_task.items():
        tc = task_contexts.get(tid)
        if tc is not None:
            latest_mm = next(
                (n.mental_model for n in reversed(notes) if n.mental_model is not None),
                None,
            )
            # Tiered delivery: cap notes per task to avoid bloating resume context
            capped = notes[-_RESUME_NOTES_PER_TASK:]
            result.append(
                ResumedTaskNotes(
                    task=tc,
                    notes=[NoteDetail.from_model(n) for n in capped],
                    latest_mental_model=latest_mm,
                )
            )
    return result
