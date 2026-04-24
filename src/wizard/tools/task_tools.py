import logging

import sentry_sdk
from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation
from mcp.shared.exceptions import McpError

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
    MissingResponse,
    NoteDetail,
    RewindResponse,
    RewindSummary,
    SaveNoteResponse,
    Signal,
    TaskContext,
    TaskStartResponse,
    TimelineEntry,
    UpdateTaskResponse,
)
from ..security import SecurityService
from ..skills import SKILL_TASK_START, load_skill_post
from .task_fields import apply_task_fields

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_VALID_STATUSES = {s.value for s in TaskStatus}

logger = logging.getLogger(__name__)


_KEY_NOTES_CAP = 5  # max notes returned by task_start


def _select_key_notes(notes_desc: list) -> list:
    """Select the most informative notes for task_start context.

    Priority (hard-ordered, total capped at _KEY_NOTES_CAP):
    1. All decision notes — resolved choices are always load-bearing.
    2. Notes with mental_models — explicit understanding captures; already
       distilled into rolling_summary but useful as anchors.
    3. Fill remaining slots with most recent notes not already selected.

    Returns notes sorted oldest-first for readability.
    """
    selected = []
    seen: set[int] = set()

    for n in notes_desc:
        if n.note_type == NoteType.DECISION and n.id is not None and n.id not in seen:
            selected.append(n)
            seen.add(n.id)

    for n in notes_desc:
        if n.mental_model is not None and n.id is not None and n.id not in seen:
            selected.append(n)
            seen.add(n.id)

    for n in notes_desc:
        if len(selected) >= _KEY_NOTES_CAP:
            break
        if n.id is not None and n.id not in seen:
            selected.append(n)
            seen.add(n.id)

    return sorted(selected, key=lambda x: x.created_at)


async def task_start(
    ctx: Context,
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
) -> TaskStartResponse:
    """Returns task context + rolling_summary + key notes (decisions, mental models, recent).

    Returns at most 5 notes, prioritising decisions and notes with mental models.
    For full note history use rewind_task.

    task_id: integer task ID from the open_tasks or blocked_tasks list
    returned by session_start. Call session_start first to get available IDs.
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
            prior_notes = [
                NoteDetail.from_model(n) for n in key_notes if n.id is not None
            ]

            latest_mental_model = next(
                (n.mental_model for n in all_notes if n.mental_model is not None),
                None,
            )

            task_state = t_state_repo.get_by_task_id(db, task_id)
            rolling_summary = task_state.rolling_summary if task_state else None
            total_notes = len(all_notes)

            # Dedup skill_instructions within the session: send only on first task_start call
            skill_delivered = await ctx.get_state("task_start_skill_delivered")
            skill = None if skill_delivered else load_skill_post(SKILL_TASK_START)
            if not skill_delivered:
                await ctx.set_state("task_start_skill_delivered", True)

            await ctx.info(f"Task {task.id} loaded: {task.name!r}.")
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
        # Capture unexpected exceptions in Sentry
        sentry_sdk.capture_exception(e)
        raise


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
    """Scrub and persist a note. Types: investigation|decision|docs|learnings|session_summary."""
    logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            task = t_repo.get_by_id(db, task_id)
            if (
                note_type in (NoteType.INVESTIGATION, NoteType.DECISION)
                and mental_model is None
            ):
                try:
                    result = await ctx.elicit(
                        "Optional: summarise what you now understand in 1-2 sentences "
                        "(mental model). Press Enter to skip.",
                        response_type=str,
                    )
                    if isinstance(result, AcceptedElicitation) and result.data:
                        mental_model = sec.scrub(result.data).clean
                except (NotImplementedError, AttributeError, McpError) as e:
                    logger.debug("ctx.elicit unavailable for mental_model: %s", e)
            if len(content) > 100_000:
                raise ToolError("Content exceeds 100k character limit")
            clean = sec.scrub(content).clean
            if mental_model is not None:
                mental_model = sec.scrub(mental_model).clean
            note = Note(
                note_type=note_type,
                content=clean,
                mental_model=mental_model,
                task_id=task.id,
                session_id=session_id,
                artifact_id=task.artifact_id,
                artifact_type="task",
            )
            saved = n_repo.save(db, note)
            if saved.id is None:
                raise ToolError(
                    "Internal error: note was not assigned an id after flush"
                )
            await ctx.report_progress(1, 2)
            t_state_repo.on_note_saved(db, task_id)
            await ctx.report_progress(2, 2)
            await ctx.info(f"Note {saved.id} saved ({note_type.value}).")
            return SaveNoteResponse(
                note_id=saved.id,
                mental_model_saved=saved.mental_model is not None,
            )
    except ValueError as e:
        logger.warning("save_note failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        # Capture unexpected exceptions in Sentry
        sentry_sdk.capture_exception(e)
        raise


async def update_task(
    ctx: Context,
    task_id: int,
    status: TaskStatus | None = None,
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
        with get_session() as db:
            task = t_repo.get_by_id(db, task_id)

            updated_fields = apply_task_fields(
                task,
                sec,
                status=status,
                priority=priority,
                due_date=due_date,
                name=name,
                source_url=source_url,
            )

            t_repo.save(db, task)
            await ctx.debug(f"Task {task_id} updated: {updated_fields}.")

            task_id_int = task.id
            if task_id_int is None:
                raise ToolError(
                    "Internal error: task was not assigned an id after flush"
                )

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
        # Capture unexpected exceptions in Sentry
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
    status: str = "todo",
    meeting_id: int | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    sec: SecurityService = Depends(get_security),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
    m_repo: MeetingRepository = Depends(get_meeting_repo),
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    logger.info("create_task priority=%s category=%s", priority.value, category.value)

    # Validate status
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status {status!r}. Valid values: {sorted(_VALID_STATUSES)}"
        )

    with get_session() as db:
        # Dedup by source_id
        if source_id:
            existing = t_repo.get_by_source_id(db, source_id)
            if existing:
                existing_id = existing.id
                if existing_id is None:
                    raise ToolError(
                        "Internal error: existing task has no id"
                    )
                # Don't update completed or archived tasks
                if existing.status in (TaskStatus.DONE, TaskStatus.ARCHIVED):
                    return CreateTaskResponse(task_id=existing_id, already_existed=True)
                scrubbed_name = sec.scrub(name).clean
                existing.name = scrubbed_name
                existing.priority = priority
                if source_url and not existing.source_url:
                    existing.source_url = source_url
                t_repo.save(db, existing)
                return CreateTaskResponse(task_id=existing_id, already_existed=True)

        clean_name = sec.scrub(name).clean
        task_status = TaskStatus(status)
        task = Task(
            name=clean_name,
            priority=priority,
            category=category,
            status=task_status,
            source_id=source_id,
            source_type=source_type,
            source_url=source_url,
        )
        t_repo.save(db, task)
        if task.id is None:
            raise ToolError("Internal error: task was not assigned an id after flush")
        await ctx.info(f"Task {task.id} created: {clean_name!r}.")
        t_state_repo.create_for_task(db, task)

        if meeting_id:
            m_repo.link_tasks(db, meeting_id, [task.id])

        return CreateTaskResponse(
            task_id=task.id,
            already_existed=False,
        )


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
        # Filter persisted notes only (id is None for unpersisted models; DB rows always have id)
        notes_asc = [n for n in reversed(notes_desc) if n.id is not None]

        timeline = [
            TimelineEntry(
                note_id=n.id,  # type: ignore[arg-type]  # id is not None: filtered above
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
            total_notes=total_notes,
            duration_days=duration_days,
            last_activity=last_activity,
        )

        task_ctx = TaskContext.from_model(task, task_state)

        return RewindResponse(task=task_ctx, timeline=timeline, summary=summary)


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


# Register tools with MCP
mcp.tool()(task_start)
mcp.tool()(save_note)
mcp.tool()(update_task)
mcp.tool()(create_task)
mcp.tool()(rewind_task)
mcp.tool()(what_am_i_missing)
