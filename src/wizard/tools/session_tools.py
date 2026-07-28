import datetime
import logging
import os
from typing import Literal

import sentry_sdk
from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from sqlalchemy import delete as sa_delete
from sqlalchemy import text

from ..config import settings
from ..database import get_session
from ..deps import (
    get_graph_memory_service,
    get_meeting_repo,
    get_note_repo,
    get_security,
    get_session_closer,
    get_task_repo,
    get_task_state_repo,
)
from ..graph_memory import GraphMemoryService, session_body
from ..mcp_instance import mcp
from ..models import Note, NoteType, ToolCall, WizardSession
from ..repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
    find_latest_session_with_notes,
)
from ..schemas import (
    SESSION_FIELD_MAX_CHARS,
    ResumeSessionResponse,
    SessionEndResponse,
    SessionStartResponse,
    SessionState,
)
from ..security import SecurityService, is_safe_session_id
from ..services import SessionCloser
from ..skills import (
    SKILL_SESSION_END,
    SKILL_SESSION_RESUME,
    load_skill_post,
)
from ..tool_call_buffer import tool_call_buffer
from .formatting import spawn_background, try_notify
from .mode_tools import build_available_modes
from .session_helpers import (
    build_prior_summaries,
    build_wizard_context,
    deserialise_session_state,
    find_previous_session_id,
    group_prior_notes,
)

logger = logging.getLogger(__name__)


def _scrub_field(sec: SecurityService, value: str | None, field_name: str) -> str | None:
    """Scrub PII from a single field, logging if modified. Returns None unchanged."""
    if value is None:
        return None
    result = sec.scrub(value)
    if result.was_modified:
        logger.info("PII scrubbed from %s", field_name)
    return result.clean


def _apply_default_mode(session: WizardSession) -> None:
    """Apply default mode to session if not already set and allowed."""
    if (
        session.active_mode is None
        and settings.modes.default
        and settings.modes.default in settings.modes.allowed
    ):
        session.active_mode = settings.modes.default


async def _detect_skill_candidate(ctx: Context, summary: str, intent: str) -> str | None:
    prompt = (
        "Review this session summary and intent. Did this session demonstrate a reusable "
        "problem-solving pattern worth turning into a skill?\n\n"
        f"Intent: {intent}\n"
        f"Summary: {summary}\n\n"
        "If yes, describe the pattern in 2-3 sentences covering: what the pattern is, "
        "when to apply it, and the key steps. "
        "If no reusable pattern is present, return exactly: null"
    )
    result = await ctx.sample(prompt)
    text = (result.text or "").strip()
    if not text or text.lower() == "null":
        return None
    return text


async def session_start(
    ctx: Context,
    agent_session_id: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
    ts_repo: TaskStateRepository = Depends(get_task_state_repo),
    session_closer: SessionCloser = Depends(get_session_closer),
) -> SessionStartResponse:
    """Create a session, return open/blocked tasks + unsummarised meetings."""
    logger.info("session_start agent_session_id=%s", agent_session_id)

    if agent_session_id and not is_safe_session_id(agent_session_id):
        logger.warning("session_start: unsafe agent_session_id %r — ignoring", agent_session_id)
        agent_session_id = None

    # Read session source from hook-written keyed directory.
    source = "startup"
    if agent_session_id:
        source_file = settings.paths.sessions_dir / agent_session_id / "source"
        if source_file.exists():
            source = source_file.read_text().strip() or "startup"

    # Compaction: link to the session that was compacted.
    continued_from_id: int | None = None
    if source == "compact":
        continued_from_id = find_previous_session_id()

    with get_session() as db:
        session = WizardSession(
            continued_from_id=continued_from_id,
            agent_session_id=agent_session_id,
            agent="claude-code" if agent_session_id else None,
            pid=os.getpid(),
        )
        db.add(session)
        db.flush()
        db.refresh(session)
        if session.id is None:
            raise ToolError(
                "Internal error: session was not assigned an id after flush"
            )

        # Apply default mode if none set and config specifies one
        _apply_default_mode(session)
        db.flush()

        await ctx.set_state("current_session_id", session.id)

        # Write wizard integer ID to the agent-session keyed directory.
        if agent_session_id:
            keyed_dir = settings.paths.sessions_dir / agent_session_id
            keyed_dir.mkdir(parents=True, exist_ok=True)
            (keyed_dir / "wizard_id").write_text(str(session.id))

        await try_notify(ctx.info(f"Session {session.id} started (source={source})."))

        closed_sessions = await session_closer.close_recent_abandoned(
            db, session.id
        )
        await try_notify(ctx.report_progress(1, 4))

        try:
            ts_repo.refresh_stale_days(db)
        except Exception as e:
            logger.warning("refresh_stale_days failed: %s", e)

        await try_notify(ctx.report_progress(2, 4))

        open_tasks_total = t_repo.count_open_tasks(db)
        open_tasks_index = t_repo.get_open_task_index(db, limit=20)
        blocked_index = t_repo.get_blocked_task_index(db)

        await try_notify(ctx.report_progress(3, 4))

        prior_summaries = build_prior_summaries(db, session.id)

        response = SessionStartResponse(
            session_id=session.id,
            continued_from_id=continued_from_id,
            source=source,
            open_tasks=open_tasks_index,
            open_tasks_total=open_tasks_total,
            blocked_tasks=blocked_index,
            unsummarised_meetings=m_repo.get_unsummarised_contexts(db),
            wizard_context=build_wizard_context(),
            closed_sessions=closed_sessions,
            prior_summaries=prior_summaries,
            active_mode=session.active_mode,
            available_modes=build_available_modes(settings.modes),
        )

    await try_notify(ctx.report_progress(4, 4))

    # Background task dispatched AFTER db context closes so it gets its own clean session
    spawn_background(session_closer.close_abandoned_background(response.session_id))

    return response


def _scrub_session_state(
    sec: SecurityService,
    intent: str,
    working_set: list[int],
    state_delta: str,
    open_loops: list[str],
    next_actions: list[str],
    closure_status: Literal["clean", "interrupted", "blocked"],
    tool_registry: str | None,
) -> tuple[SessionState, str]:
    """Scrub PII from session state fields, cap length, and return state + clean intent."""

    state = SessionState(
        intent=(_scrub_field(sec, intent, "session intent") or "")[:SESSION_FIELD_MAX_CHARS],
        working_set=working_set,
        state_delta=(_scrub_field(sec, state_delta, "state_delta") or "")[
            :SESSION_FIELD_MAX_CHARS
        ],
        open_loops=[
            (_scrub_field(sec, loop, "open_loop") or loop)[:SESSION_FIELD_MAX_CHARS]
            for loop in open_loops
        ],
        next_actions=[
            (_scrub_field(sec, action, "next_action") or action)[:SESSION_FIELD_MAX_CHARS]
            for action in next_actions
        ],
        closure_status=closure_status,
        tool_registry=tool_registry,
    )
    return state, state.intent


async def push_session_episode(
    gms: GraphMemoryService,
    session_id: int,
    state: SessionState,
) -> None:
    """Dual-write a session episode to Graphiti. push_episode is sync and internally
    guarded by `enabled`; this thunk just keeps it on the spawn_background seam."""
    gms.push_episode(
        entity_type="session", entity_id=session_id,
        name=f"session {session_id}",
        reference_time=datetime.datetime.now(),
        body=session_body(
            intent=state.intent, state_delta=state.state_delta,
            open_loops=state.open_loops, next_actions=state.next_actions,
            closure_status=state.closure_status,
        ),
    )


async def _persist_session_end(
    ctx: Context,
    session_id: int,
    summary: str,
    intent: str,
    working_set: list[int],
    state_delta: str,
    open_loops: list[str],
    next_actions: list[str],
    closure_status: Literal["clean", "interrupted", "blocked"],
    tool_registry: str | None,
    sec: SecurityService,
    n_repo: NoteRepository,
    gms: GraphMemoryService,
) -> SessionEndResponse:
    """Write session close state and summary note to the DB; return response."""
    state, clean_intent = _scrub_session_state(
        sec, intent, working_set, state_delta, open_loops, next_actions,
        closure_status, tool_registry,
    )

    with get_session() as db:
        session = db.get(WizardSession, session_id)
        if session is None:
            await ctx.error(f"Session {session_id} not found")
            raise ToolError(f"Session {session_id} not found")
        if session.closed_by is not None:
            await ctx.error(f"Session {session_id} was already closed")
            raise ToolError(
                f"Session {session_id} was already closed (closed_by={session.closed_by!r})"
            )

        session_state_saved = False
        try:
            session.session_state = state.model_dump_json()
            session_state_saved = True
        except (ValueError, TypeError) as e:
            logger.warning("session_end: failed to serialise session_state: %s", e)

        clean_summary = _scrub_field(sec, summary, "session summary")
        session.closed_by = "user"
        session.summary = clean_summary
        db.add(session)
        db.flush()
        db.refresh(session)
        if session.id is None:
            raise ToolError("Internal error: session was not assigned an id after flush")

        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary or "",
            session_id=session.id,
            artifact_id=session.artifact_id,
            artifact_type="session",
        )
        saved = n_repo.save(db, note)
        if saved.id is None:
            raise ToolError("Internal error: note was not assigned an id after flush")

        await ctx.delete_state("current_session_id")
        await try_notify(ctx.info(
            f"Session {session.id} closed. Status: {closure_status}. "
            f"{len(open_loops)} open loop(s), {len(next_actions)} next action(s)."
        ))

        await tool_call_buffer.flush_now(db)

        cutoff = datetime.datetime.now() - datetime.timedelta(days=90)
        db.execute(sa_delete(ToolCall).where(ToolCall.called_at < cutoff))

        response = SessionEndResponse(
            note_id=saved.id,
            session_state_saved=session_state_saved,
            closure_status=closure_status,
            open_loops_count=len(open_loops),
            next_actions_count=len(next_actions),
            intent=clean_intent,
            skill_instructions=load_skill_post(SKILL_SESSION_END),
        )

    spawn_background(push_session_episode(gms, session_id, state))

    with get_session() as maint_db:
        try:
            maint_db.execute(text("PRAGMA incremental_vacuum(100)"))
            maint_db.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
        except Exception as e:
            logger.warning("session_end: maintenance PRAGMAs skipped: %s", e)

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
    gms: GraphMemoryService = Depends(get_graph_memory_service),
) -> SessionEndResponse:
    """Persists session summary + SessionState to WizardSession."""
    logger.info("session_end session_id=%d", session_id)
    try:
        response = await _persist_session_end(
            ctx, session_id, summary, intent, working_set, state_delta,
            open_loops, next_actions, closure_status, tool_registry, sec, n_repo, gms,
        )
    except ValueError as e:
        logger.warning("session_end failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise

    if working_set:
        try:
            response.skill_candidate = await _detect_skill_candidate(ctx, summary, intent)
        except Exception as e:
            logger.warning("session_end: skill candidate detection failed: %s", e)

    return response


async def resume_session(
    ctx: Context,
    session_id: int | None = None,
    agent_session_id: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
) -> ResumeSessionResponse:
    """Resume a prior session in a new thread. Creates a new session."""
    logger.info("resume_session session_id=%s", session_id)

    if agent_session_id and not is_safe_session_id(agent_session_id):
        logger.warning("resume_session: unsafe agent_session_id %r — ignoring", agent_session_id)
        agent_session_id = None

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
            raise ToolError(
                "Internal error: session was not assigned an id after flush"
            )

        # Resumed sessions explicitly continue from the source session.
        new_session = WizardSession(
            continued_from_id=prior.id,
            pid=os.getpid(),
        )
        db.add(new_session)
        db.flush()
        db.refresh(new_session)
        if new_session.id is None:
            raise ToolError(
                "Internal error: session was not assigned an id after flush"
            )
        await ctx.set_state("current_session_id", new_session.id)
        await try_notify(ctx.info(f"Resumed session {new_session.id} (from {prior.id})."))

        # Write wizard integer ID to the agent-session keyed directory (mirrors session_start).
        if agent_session_id and new_session.id is not None:
            keyed_dir = settings.paths.sessions_dir / agent_session_id
            keyed_dir.mkdir(parents=True, exist_ok=True)
            (keyed_dir / "wizard_id").write_text(str(new_session.id))

        session_state, working_set_tasks = deserialise_session_state(db, prior, t_repo)

        prior_notes = group_prior_notes(db, prior.id, n_repo, t_repo)

        return ResumeSessionResponse(
            session_id=new_session.id,
            resumed_from_session_id=prior.id,
            continued_from_id=prior.id,
            session_state=session_state,
            working_set_tasks=working_set_tasks,
            prior_notes=prior_notes,
            unsummarised_meetings=m_repo.get_unsummarised_contexts(db),
            skill_instructions=load_skill_post(SKILL_SESSION_RESUME),
            active_mode=prior.active_mode,
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(session_start)
mcp.tool()(session_end)
mcp.tool()(resume_session)
