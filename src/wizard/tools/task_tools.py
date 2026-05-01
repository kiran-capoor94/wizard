import hashlib
import logging
from typing import Annotated

import sentry_sdk
from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from pydantic import BeforeValidator

from ..database import get_session
from ..deps import get_meeting_repo, get_note_repo, get_security, get_task_repo, get_task_state_repo
from ..mcp_instance import mcp
from ..models import (
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskStatus,
)
from ..repositories import MeetingRepository, NoteRepository, TaskRepository, TaskStateRepository
from ..schemas import (
    CreateTaskResponse,
    NoteDetail,
    SaveNoteResponse,
    TaskStartResponse,
    UpdateTaskResponse,
)
from ..security import SecurityService
from ..skills import SKILL_TASK_START, load_skill_post
from .formatting import try_notify
from .task_fields import (
    apply_task_fields,
    check_duplicate_name,
    elicit_done_confirmation,
)

_STATUS_ALIASES: dict[str, str] = {
    "completed": "done",
    "complete": "done",
    "finish": "done",
    "finished": "done",
    "open": "todo",
    "pending": "todo",
    "wip": "in_progress",
    "doing": "in_progress",
    "inactive": "archived",
}


def _normalize_status(v: object) -> object:
    if isinstance(v, str):
        return _STATUS_ALIASES.get(v.lower(), v)
    return v


NullableTaskStatus = Annotated[TaskStatus | None, BeforeValidator(_normalize_status)]
TaskStatusWithDefault = Annotated[TaskStatus, BeforeValidator(_normalize_status)]

logger = logging.getLogger(__name__)

_KEY_NOTES_CAP = 5  # max notes returned by task_start


def _add_tier_notes(
    selected: list,
    seen: set[int],
    notes: list,
) -> None:
    """Add notes from a tier until cap is reached. Modifies selected and seen in place."""
    for n in sorted(notes, key=lambda x: x.created_at):
        if len(selected) >= _KEY_NOTES_CAP:
            break
        if n.id is not None and n.id not in seen:
            selected.append(n)
            seen.add(n.id)


def _select_key_notes(notes_desc: list) -> list:
    """Select the most informative notes for task_start context.

    Priority (hard-ordered, total capped at _KEY_NOTES_CAP):
    0. All failure notes — what didn't work is load-bearing context.
    1. All decision notes — resolved choices are always load-bearing.
    2. Notes with mental_models — explicit understanding captures.
    3. Fill remaining slots with most recent notes not already selected.

    Returns notes in priority order (oldest-first within each tier for readability).
    """
    selected = []
    seen: set[int] = set()

    # Tier 0: failure notes (oldest-first within tier)
    failure_notes = [
        n for n in notes_desc
        if n.note_type == NoteType.FAILURE and n.id is not None
    ]
    _add_tier_notes(selected, seen, failure_notes)

    # Tier 1: decision notes (oldest-first within tier)
    decision_notes = [
        n for n in notes_desc
        if n.note_type == NoteType.DECISION and n.id is not None
    ]
    _add_tier_notes(selected, seen, decision_notes)

    # Tier 2: notes with mental models (oldest-first within tier)
    mental_model_notes = [
        n for n in notes_desc
        if n.mental_model is not None and n.id is not None
    ]
    _add_tier_notes(selected, seen, mental_model_notes)

    # Tier 3: fill remaining slots with most recent notes (newest-first)
    remaining = [
        n for n in notes_desc
        if n.id is not None and n.id not in seen
    ]
    _add_tier_notes(selected, seen, remaining)

    return selected


async def task_start(
    ctx: Context,
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
) -> TaskStartResponse:
    """Returns task context + rolling_summary + key notes (decisions, mental models, recent).

    Returns at most 5 notes, prioritising decisions and notes with mental models.
    For full note history use rewind_task. task_id must come from session_start.
    """
    logger.info("task_start task_id=%d", task_id)
    try:
        with get_session() as db:
            task = t_repo.get_by_id(db, task_id)
            task_ctx = t_repo.get_task_context(db, task)

            # All notes descending: used for counts, selection, and rolling_summary lookup.
            all_notes = n_repo.get_for_task(db, task_id=task.id)
            notes_by_type: dict[str, int] = {}
            for note in all_notes:
                key = note.note_type.value
                notes_by_type[key] = notes_by_type.get(key, 0) + 1

            key_notes = _select_key_notes(all_notes)
            prior_notes = [NoteDetail.from_model(n) for n in key_notes if n.id is not None]
            latest_mental_model = next(
                (n.mental_model for n in all_notes if n.mental_model is not None), None
            )
            task_state = t_state_repo.get_by_task_id(db, task_id)
            rolling_summary = task_state.rolling_summary if task_state else None
            total_notes = len(all_notes)
            # Dedup skill_instructions within the session: send only on first task_start call
            skill_delivered = await ctx.get_state("task_start_skill_delivered")
            skill = None if skill_delivered else load_skill_post(SKILL_TASK_START)
            if not skill_delivered:
                await ctx.set_state("task_start_skill_delivered", True)

            await try_notify(ctx.info(f"Task {task.id} loaded: {task.name!r}."))
            return TaskStartResponse(
                task=task_ctx,
                compounding=total_notes > 0,
                notes_by_type=notes_by_type,
                prior_notes=prior_notes,
                total_notes=total_notes,
                older_notes_available=len(key_notes) < total_notes,
                rolling_summary=rolling_summary,
                latest_mental_model=latest_mental_model,
                skill_instructions=skill,
            )
    except ValueError as e:
        logger.warning("task_start failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise


async def compress_note_content(ctx: Context, content: str) -> str:
    """Compress content to under 1000 chars via LLM, preserving technical specifics."""
    result = await ctx.sample(
        f"Compress the following note to under 1000 characters. "
        f"Preserve all file paths, function names, line numbers, error messages, "
        f"decisions, and technical specifics exactly. Remove filler words and "
        f"redundant phrasing only. Return only the compressed note, no preamble.\n\n"
        f"{content}"
    )
    compressed = result.text.strip()
    return compressed[:1000] if len(compressed) > 1000 else compressed


async def _prepare_note_fields(
    ctx: Context,
    sec: SecurityService,
    content: str,
    mental_model: str | None,
) -> tuple[str, str | None, str]:
    """Compress (if needed), scrub PII, and hash content. Returns (clean, mental_model, hash)."""
    if len(content) > 1000:
        content = await compress_note_content(ctx, content)
    if mental_model is not None and len(mental_model) > 1000:
        mental_model = await compress_note_content(ctx, mental_model)
    scrub_result = sec.scrub(content)
    if scrub_result.was_modified:
        logger.info("PII scrubbed from note content")
    clean = scrub_result.clean
    if mental_model is not None:
        mm_scrub = sec.scrub(mental_model)
        if mm_scrub.was_modified:
            logger.info("PII scrubbed from mental_model")
        mental_model = mm_scrub.clean
    content_hash = hashlib.sha256(clean.encode()).hexdigest()
    return clean, mental_model, content_hash


def _persist_note(
    n_repo: NoteRepository,
    t_state_repo: TaskStateRepository,
    note_type: NoteType,
    clean: str,
    mental_model: str | None,
    task_db_id: int,
    session_id: int | None,
    task_artifact_id: str | None,
    content_hash: str,
) -> SaveNoteResponse:
    """Dedup-check then write note. Returns SaveNoteResponse."""
    with get_session() as db:
        existing = n_repo.get_by_content_hash(db, task_db_id, content_hash)
        if existing is not None and existing.id is not None:
            if mental_model is not None and existing.mental_model is None:
                existing.mental_model = mental_model
                db.add(existing)
                db.flush()
            return SaveNoteResponse(
                note_id=existing.id,
                mental_model_saved=existing.mental_model is not None,
                was_duplicate=True,
            )
        note = Note(
            note_type=note_type,
            content=clean,
            mental_model=mental_model,
            task_id=task_db_id,
            session_id=session_id,
            artifact_id=task_artifact_id,
            artifact_type="task",
            synthesis_content_hash=content_hash,
        )
        saved = n_repo.save(db, note)
        if saved.id is None:
            raise ToolError("Internal error: note was not assigned an id after flush")
        t_state_repo.on_note_saved(db, task_db_id, note_type, saved.created_at)
        return SaveNoteResponse(
            note_id=saved.id,
            mental_model_saved=saved.mental_model is not None,
            was_duplicate=False,
        )


async def save_note(
    ctx: Context,
    task_id: int,
    note_type: NoteType,
    content: str,
    mental_model: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    sec: SecurityService = Depends(get_security),
    n_repo: NoteRepository = Depends(get_note_repo),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
) -> SaveNoteResponse:
    """Scrub and persist a note.

    Types: investigation|decision|docs|learnings|session_summary|failure.
    """
    logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)
    try:
        # Phase 1: fetch task metadata, then close DB.
        session_id: int | None = await ctx.get_state("current_session_id")
        with get_session() as db:
            task = t_repo.get_by_id(db, task_id)
            task_artifact_id = task.artifact_id
            if task.id is None:
                raise ToolError("Internal error: task has no id")
            task_db_id: int = task.id

        # Phase 2: validate size limit.
        if len(content) > 100_000:
            raise ToolError("Content exceeds 100k character limit")

        # Phase 3: compress, scrub, dedup, and write.
        clean, mental_model, content_hash = await _prepare_note_fields(
            ctx, sec, content, mental_model
        )
        result = _persist_note(
            n_repo, t_state_repo, note_type, clean, mental_model,
            task_db_id, session_id, task_artifact_id, content_hash,
        )
        await try_notify(ctx.report_progress(1, 2))
        await try_notify(ctx.report_progress(2, 2))
        await try_notify(ctx.info(f"Note {result.note_id} saved ({note_type.value})."))
        return result
    except ValueError as e:
        logger.warning("save_note failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise


async def update_task(
    ctx: Context,
    task_id: int,
    status: NullableTaskStatus = None,
    priority: TaskPriority | None = None,
    due_date: str | None = None,
    name: str | None = None,
    source_url: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    sec: SecurityService = Depends(get_security),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
) -> UpdateTaskResponse:
    """Atomically update task fields. Only provided (non-None) fields are updated.

    Raises ToolError if no fields are provided or task not found.
    """
    logger.info("update_task task_id=%d", task_id)
    if all(v is None for v in [status, priority, due_date, name, source_url]):
        raise ToolError("At least one field must be provided to update_task")

    try:
        # Phase 1: fetch task name for elicitation prompt, then close DB.
        with get_session() as db:
            task = t_repo.get_by_id(db, task_id)
            task_name = task.name

        # Phase 2: elicit done confirmation outside DB context.
        if status == TaskStatus.DONE and not await elicit_done_confirmation(ctx, task_name):
            return UpdateTaskResponse(task_id=task_id, updated_fields=[], task_state_updated=False)

        # Phase 3: apply updates.
        with get_session() as db:
            task = t_repo.get_by_id(db, task_id)
            updated_fields = apply_task_fields(
                task, sec,
                status=status, priority=priority,
                due_date=due_date, name=name, source_url=source_url,
            )
            t_repo.save(db, task)
            task_id_int = task.id
            if task_id_int is None:
                raise ToolError("Internal error: task was not assigned an id after flush")
            await try_notify(ctx.debug(f"Task {task_id} updated: {updated_fields}."))
            task_state_updated = False
            if "status" in updated_fields:
                t_state_repo.on_status_changed(db, task_id_int)
                task_state_updated = True

        return UpdateTaskResponse(
            task_id=task_id_int,
            updated_fields=updated_fields,
            task_state_updated=task_state_updated,
        )
    except ValueError as e:
        logger.warning("update_task failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise


async def create_task(
    ctx: Context,
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    source_id: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    status: TaskStatusWithDefault = TaskStatus.TODO,
    meeting_id: int | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    sec: SecurityService = Depends(get_security),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    logger.info("create_task priority=%s category=%s", priority.value, category.value)

    # Scrub name once; audit if PII was detected.
    _name_scrub = sec.scrub(name)
    if _name_scrub.was_modified:
        logger.info("PII scrubbed from create_task name")
    clean_name = _name_scrub.clean

    # Phase 1: source_id upsert — no elicitation needed; one DB context.
    if source_id:
        with get_session() as db:
            existing = t_repo.upsert_by_source_id(
                db, source_id, clean_name, priority, source_url
            )
            if existing and existing.id is not None:
                return CreateTaskResponse(task_id=existing.id, already_existed=True)
        blocked_by = None
    else:
        # Phase 1: fetch names, close DB.  Phase 2: elicit outside DB context.
        with get_session() as db:
            existing_names = t_repo.get_active_task_names(db)
        blocked_by = await check_duplicate_name(ctx, name, existing_names)

    # Phase 3: create or return existing — single transaction eliminates TOCTOU window.
    with get_session() as db:
        if blocked_by is not None:
            # Re-fetch inside this transaction: if task was renamed/deleted since
            # elicitation, get_by_name returns None and we fall through to create.
            existing = t_repo.get_by_name(db, blocked_by)
            if existing and existing.id is not None:
                return CreateTaskResponse(task_id=existing.id, already_existed=True)
        task = Task(
            name=clean_name,
            priority=priority,
            category=category,
            status=status,
            source_id=source_id,
            source_type=source_type,
            source_url=source_url,
        )
        t_repo.save(db, task)
        if task.id is None:
            raise ToolError("Internal error: task was not assigned an id after flush")
        task_id = task.id
        t_state_repo.create_for_task(db, task)
        if meeting_id:
            m_repo.link_tasks(db, meeting_id, [task_id])
    await try_notify(ctx.info(f"Task {task_id} created: {clean_name!r}."))
    return CreateTaskResponse(task_id=task_id, already_existed=False)


# Register tools with MCP
mcp.tool()(task_start)
mcp.tool()(save_note)
mcp.tool()(update_task)
mcp.tool()(create_task)
