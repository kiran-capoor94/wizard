import logging
from typing import Literal

import httpx
import sqlalchemy.exc
from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from notion_client.errors import APIResponseError
from pydantic import ValidationError
from sqlmodel import Session

from ..database import get_session
from ..deps import (
    get_meeting_repo,
    get_note_repo,
    get_notion_client,
    get_security,
    get_sync_service,
    get_task_repo,
    get_task_state_repo,
    get_writeback,
)
from ..integrations import NotionClient
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
from ..services import SyncService, WriteBackService
from ..skills import SKILL_SESSION_END, SKILL_SESSION_RESUME, SKILL_SESSION_START, load_skill

logger = logging.getLogger(__name__)


def _init_session(db: Session, notion: NotionClient) -> "tuple[WizardSession, object]":
    """Create a new WizardSession and attach the daily page if available."""
    session = WizardSession()
    db.add(session)
    db.flush()
    db.refresh(session)
    if session.id is None:
        raise ToolError("Internal error: session was not assigned an id after flush")
    daily_page = None
    try:
        daily_page = notion.ensure_daily_page()
        session.daily_page_id = daily_page.page_id
        db.add(session)
        db.flush()
    except (APIResponseError, httpx.HTTPError, KeyError, TypeError) as e:
        logger.warning("ensure_daily_page failed: %s", e)
    return session, daily_page


async def session_start(
    ctx: Context,
    sync_svc: SyncService = Depends(get_sync_service),
    notion: NotionClient = Depends(get_notion_client),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
    t_repo: TaskRepository = Depends(get_task_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
) -> SessionStartResponse:
    """Create a session, sync Jira/Notion, return open/blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session, daily_page = _init_session(db, notion)

        sync_results = sync_svc.sync_all(db)
        await ctx.report_progress(1, 1, "Sync complete.")

        await ctx.set_state("current_session_id", session.id)
        await ctx.info(f"Session {session.id} started.")

        try:
            t_state_repo.refresh_stale_days(db)
        except sqlalchemy.exc.SQLAlchemyError as e:
            logger.warning("refresh_stale_days failed: %s", e)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=t_repo.get_open_task_contexts(db),
            blocked_tasks=t_repo.get_blocked_task_contexts(db),
            unsummarised_meetings=m_repo.get_unsummarised_contexts(db),
            sync_results=sync_results,
            daily_page=daily_page,
            skill_instructions=load_skill(SKILL_SESSION_START),
        )


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
    wb: WriteBackService = Depends(get_writeback),
) -> SessionEndResponse:
    """Persists session summary + SessionState to WizardSession. Writes Notion daily page."""
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

            wb_result = wb.push_session_summary(session)

            await ctx.delete_state("current_session_id")
            await ctx.info(
                f"Session {session.id} closed. Status: {closure_status}. "
                f"{len(open_loops)} open loop(s), {len(next_actions)} next action(s)."
            )

            return SessionEndResponse(
                note_id=saved.id,
                notion_write_back=wb_result,
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
    sync_svc: SyncService = Depends(get_sync_service),
    notion: NotionClient = Depends(get_notion_client),
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
) -> ResumeSessionResponse:
    """Resume a prior session in a new thread. Creates a new session and syncs."""
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
        new_session, daily_page = _init_session(db, notion)

        # Sync
        sync_results = sync_svc.sync_all(db)

        session_state, working_set_tasks = _deserialise_session_state(db, prior, t_repo)

        prior_notes = _group_prior_notes(db, prior.id, n_repo, t_repo)

        return ResumeSessionResponse(
            session_id=new_session.id,
            resumed_from_session_id=prior.id,
            session_state=session_state,
            working_set_tasks=working_set_tasks,
            prior_notes=prior_notes,
            unsummarised_meetings=m_repo.get_unsummarised_contexts(db),
            sync_results=sync_results,
            daily_page=daily_page,
            skill_instructions=load_skill(SKILL_SESSION_RESUME),
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(session_start)
mcp.tool()(session_end)
mcp.tool()(resume_session)
