import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from pydantic import ValidationError
from sqlmodel import Session

from ..config import settings
from ..database import get_session
from ..deps import (
    get_meeting_repo,
    get_note_repo,
    get_security,
    get_session_closer,
    get_task_repo,
    get_task_state_repo,
)
from ..mcp_instance import mcp
from ..models import (
    Note,
    NoteType,
    WizardSession,
)
from ..repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
    find_latest_session_with_notes,
)
from ..schemas import (
    NoteDetail,
    ResumedTaskNotes,
    ResumeSessionResponse,
    SessionEndResponse,
    SessionStartResponse,
    SessionState,
    TaskContext,
)
from ..security import SecurityService
from ..services import SessionCloser
from ..skills import SKILL_SESSION_END, SKILL_SESSION_RESUME, SKILL_SESSION_START, load_skill

logger = logging.getLogger(__name__)

_SESSION_ID_FILE = Path.home() / ".wizard" / "current_session_id"


def _build_wizard_context() -> dict | None:
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


async def session_start(
    ctx: Context,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
    ts_repo: TaskStateRepository = Depends(get_task_state_repo),
    session_closer: SessionCloser = Depends(get_session_closer),
) -> SessionStartResponse:
    """Create a session, return open/blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        if session.id is None:
            raise ToolError("Internal error: session was not assigned an id after flush")

        await ctx.set_state("current_session_id", session.id)
        _SESSION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_ID_FILE.write_text(str(session.id))
        await ctx.info(f"Session {session.id} started.")

        closed_sessions = await session_closer.close_recent_abandoned(db, ctx, session.id)

        try:
            ts_repo.refresh_stale_days(db)
        except Exception as e:
            logger.warning("refresh_stale_days failed: %s", e)

        open_tasks_total = t_repo.count_open_tasks(db)
        open_tasks = t_repo.get_open_task_contexts(db, limit=20)

        response = SessionStartResponse(
            session_id=session.id,
            open_tasks=open_tasks,
            open_tasks_total=open_tasks_total,
            blocked_tasks=t_repo.get_blocked_task_contexts(db),
            unsummarised_meetings=m_repo.get_unsummarised_contexts(db),
            wizard_context=_build_wizard_context(),
            skill_instructions=load_skill(SKILL_SESSION_START),
            closed_sessions=closed_sessions,
        )

    # Background task dispatched AFTER db context closes so it gets its own clean session
    asyncio.create_task(session_closer.close_abandoned_background(response.session_id))

    return response


async def session_end(
    ctx: Context,
    session_id: int,
    summary: str,
    intent: str,
    working_set: list[int],
    state_delta: str,
    open_loops: list[str],
    next_actions: list[str],
    closure_status: Literal["clean", "interrupted", "blocked"],
    tool_registry: str | None = None,
    sec: SecurityService = Depends(get_security),
    n_repo: NoteRepository = Depends(get_note_repo),
) -> SessionEndResponse:
    """Persists session summary + SessionState to WizardSession."""
    logger.info("session_end session_id=%d", session_id)
    try:
        with get_session() as db:
            session = db.get(WizardSession, session_id)
            if session is None:
                await ctx.error(f"Session {session_id} not found")
                raise ToolError(f"Session {session_id} not found")

            state = SessionState(
                intent=sec.scrub(intent).clean,
                working_set=working_set,
                state_delta=sec.scrub(state_delta).clean,
                open_loops=[sec.scrub(loop).clean for loop in open_loops],
                next_actions=[sec.scrub(action).clean for action in next_actions],
                closure_status=closure_status,
                tool_registry=tool_registry,
            )
            session_state_saved = False
            try:
                session.session_state = state.model_dump_json()
                session_state_saved = True
            except (ValueError, TypeError) as e:
                logger.warning("session_end: failed to serialise session_state: %s", e)

            clean_summary = sec.scrub(summary).clean
            session.closed_by = "user"
            session.summary = clean_summary
            db.add(session)
            db.flush()
            db.refresh(session)
            if session.id is None:
                raise ToolError("Internal error: session was not assigned an id after flush")

            note = Note(
                note_type=NoteType.SESSION_SUMMARY,
                content=clean_summary,
                session_id=session.id,
            )
            saved = n_repo.save(db, note)
            if saved.id is None:
                raise ToolError("Internal error: note was not assigned an id after flush")

            await ctx.delete_state("current_session_id")
            _SESSION_ID_FILE.unlink(missing_ok=True)
            await ctx.info(
                f"Session {session.id} closed. Status: {closure_status}. "
                f"{len(open_loops)} open loop(s), {len(next_actions)} next action(s)."
            )

            return SessionEndResponse(
                note_id=saved.id,
                session_state_saved=session_state_saved,
                closure_status=closure_status,
                open_loops_count=len(open_loops),
                next_actions_count=len(next_actions),
                intent=intent,
                skill_instructions=load_skill(SKILL_SESSION_END),
            )
    except ValueError as e:
        logger.warning("session_end failed: %s", e)
        raise ToolError(str(e)) from e


def _deserialise_session_state(
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


def _group_prior_notes(
    db: Session, session_id: int, n_repo: NoteRepository, t_repo: TaskRepository
) -> list[ResumedTaskNotes]:
    """Query notes for a session and group by task with latest mental model."""
    by_task = n_repo.get_notes_grouped_by_task(db, session_id)
    if not by_task:
        return []

    # Build a TaskContext lookup for all referenced tasks
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
            result.append(
                ResumedTaskNotes(
                    task=tc,
                    notes=[NoteDetail.from_model(n) for n in notes],
                    latest_mental_model=latest_mm,
                )
            )
    return result


async def resume_session(
    ctx: Context,
    session_id: int | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
) -> ResumeSessionResponse:
    """Resume a prior session in a new thread. Creates a new session."""
    logger.info("resume_session session_id=%s", session_id)
    with get_session() as db:
        # Find prior session
        if session_id is not None:
            prior = db.get(WizardSession, session_id)
            if prior is None:
                raise ToolError(f"Session {session_id} not found")
        else:
            prior = find_latest_session_with_notes(db)
            if prior is None:
                raise ToolError("No sessions with notes found")

        if prior.id is None:
            raise ToolError("Internal error: session was not assigned an id after flush")

        # Create new session
        new_session = WizardSession()
        db.add(new_session)
        db.flush()
        db.refresh(new_session)
        await ctx.set_state("current_session_id", new_session.id)
        _SESSION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_ID_FILE.write_text(str(new_session.id))

        session_state, working_set_tasks = _deserialise_session_state(db, prior, t_repo)

        prior_notes = _group_prior_notes(db, prior.id, n_repo, t_repo)

        return ResumeSessionResponse(
            session_id=new_session.id,
            resumed_from_session_id=prior.id,
            session_state=session_state,
            working_set_tasks=working_set_tasks,
            prior_notes=prior_notes,
            unsummarised_meetings=m_repo.get_unsummarised_contexts(db),
            skill_instructions=load_skill(SKILL_SESSION_RESUME),
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(session_start)
mcp.tool()(session_end)
mcp.tool()(resume_session)
