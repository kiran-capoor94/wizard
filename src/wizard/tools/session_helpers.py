"""Session helper functions extracted from session_tools.py to keep it under 500 lines.

Contains: wizard_context builder, prior-summaries builder, previous-session lookup.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError
from sqlmodel import Session

from ..config import settings
from ..database import get_session
from ..repositories import SessionRepository
from ..schemas import PriorSessionSummary, SessionState

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
