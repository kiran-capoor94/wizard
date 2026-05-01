"""Session helper functions extracted from session_tools.py to keep it under 500 lines.

Contains: wizard_context builder, prior-summaries builder, previous-session lookup,
mid-session synthesis loop, and the Synthesiser factory for background use.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import ValidationError
from sqlmodel import Session

from ..config import settings
from ..database import get_session
from ..models import WizardSession
from ..repositories import NoteRepository, SessionRepository, TaskRepository
from ..schemas import PriorSessionSummary, SessionState
from ..security import SecurityService
from ..synthesis import Synthesiser
from ..transcript import TranscriptReader, find_transcript, read_new_lines

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


def _make_synthesiser() -> Synthesiser:
    """Construct a fully-wired Synthesiser for background mid-session synthesis."""
    security = SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
    )
    return Synthesiser(
        reader=TranscriptReader(),
        note_repo=NoteRepository(),
        security=security,
        settings=settings,
        t_repo=TaskRepository(),
    )


def run_mid_session_synthesis(
    synthesiser: Synthesiser,
    wizard_session_id: int,
    lines: list[str],
) -> int:
    """Execute one mid-session synthesis pass in a DB transaction.

    Returns the number of lines processed (0 if session is missing).
    Extracted from the async polling loop so each abstraction layer stays flat.
    """
    with get_session() as db:
        session = db.get(WizardSession, wizard_session_id)
        if session is None:
            return 0
        synthesiser.synthesise_lines(db, session, lines)
        return len(lines)


async def mid_session_synthesis_loop(
    agent_session_id: str,
    wizard_session_id: int,
    interval_seconds: int = 300,
) -> None:
    """Poll the transcript file every `interval_seconds` and synthesise new lines.

    Tracks processed line count in a local variable — ctx.state is not used
    since this runs outside any request context. On failure, logs and retries
    next poll; SessionEnd synthesis is the guaranteed full-synthesis path.
    """
    synthesiser = _make_synthesiser()
    processed = 0
    while True:
        await asyncio.sleep(interval_seconds)
        transcript_path = find_transcript(agent_session_id)
        if not transcript_path:
            continue
        new_lines = read_new_lines(transcript_path, processed)
        if not new_lines:
            continue
        try:
            delta = await asyncio.to_thread(
                run_mid_session_synthesis, synthesiser, wizard_session_id, new_lines
            )
            processed += delta
        except Exception:
            logger.debug(
                "mid_session_synthesis: poll failed, will retry next interval",
                exc_info=True,
            )


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
