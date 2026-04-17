import datetime
import logging

from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation

from ..deps import (
    get_note_repo,
    get_security,
    get_task_repo,
    get_task_state_repo,
    get_writeback,
)
from ..mcp_instance import mcp
from ..repositories import (
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
)
from ..security import SecurityService
from ..services import WriteBackService
from ..models import (
    MeetingTasks,
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskState,
    TaskStatus,
)
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
    WriteBackStatus,
)

from . import _helpers
from ._helpers import _log_tool_call, _SEVERITY_ORDER

logger = logging.getLogger(__name__)


async def task_start(
    ctx: Context,
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context.

    task_id: integer task ID from the open_tasks or blocked_tasks list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("task_start task_id=%d", task_id)
    try:
        with _helpers.get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "task_start", session_id=session_id)
            task = t_repo.get_by_id(db, task_id)
            task_ctx = t_repo.build_task_context(db, task)

            notes = n_repo.get_for_task(
                db, task_id=task.id, source_id=task.source_id
            )
            notes_by_type: dict[str, int] = {}
            for note in notes:
                key = note.note_type.value
                notes_by_type[key] = notes_by_type.get(key, 0) + 1

            prior_notes = [NoteDetail.from_model(n) for n in reversed(notes) if n.id is not None]

            latest_mental_model = next(
                (n.mental_model for n in notes if n.mental_model is not None),
                None,
            )

            return TaskStartResponse(
                task=task_ctx,
                compounding=len(notes) > 0,
                notes_by_type=notes_by_type,
                prior_notes=prior_notes,
                latest_mental_model=latest_mental_model,
            )
    except ValueError as e:
        logger.warning("task_start failed: %s", e)
        raise ToolError(str(e)) from e


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
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)
    try:
        with _helpers.get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "save_note", session_id=session_id)
            task = t_repo.get_by_id(db, task_id)
            if (
                note_type in (NoteType.INVESTIGATION, NoteType.DECISION)
                and mental_model is None
            ):
                try:
                    result = await ctx.elicit(
                        "Optional: summarise what you now understand in 1-2 sentences (mental model). "
                        "Press Enter to skip.",
                        response_type=str,
                    )
                    if isinstance(result, AcceptedElicitation) and result.data:
                        mental_model = sec.scrub(result.data).clean
                except Exception as e:
                    logger.debug("ctx.elicit unavailable for mental_model: %s", e)
            clean = sec.scrub(content).clean
            if mental_model is not None:
                mental_model = sec.scrub(mental_model).clean
            note = Note(
                note_type=note_type,
                content=clean,
                mental_model=mental_model,
                task_id=task.id,
                source_id=task.source_id,
                source_type=task.source_type,
                session_id=session_id,
            )
            saved = n_repo.save(db, note)
            if saved.id is None:
                raise ToolError("Internal error: note was not assigned an id after flush")
            t_state_repo.on_note_saved(db, task_id)
            return SaveNoteResponse(
                note_id=saved.id,
                mental_model_saved=saved.mental_model is not None,
            )
    except ValueError as e:
        logger.warning("save_note failed: %s", e)
        raise ToolError(str(e)) from e


async def update_task(
    ctx: Context,
    task_id: int,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_date: str | None = None,
    notion_id: str | None = None,
    name: str | None = None,
    source_url: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    sec: SecurityService = Depends(get_security),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
    wb: WriteBackService = Depends(get_writeback),
) -> UpdateTaskResponse:
    """Atomically update task fields. Only provided (non-None) fields are updated.

    Raises ToolError if no fields are provided or task not found.

    Writebacks:
    - status: Jira + Notion
    - due_date: Notion only
    - priority: Notion only
    - name: local only (no external writeback)
    - source_url: local only (no external writeback)
    """
    logger.info("update_task task_id=%d", task_id)

    if all(
        v is None for v in [status, priority, due_date, notion_id, name, source_url]
    ):
        raise ToolError("At least one field must be provided to update_task")

    try:
        with _helpers.get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "update_task", session_id=session_id)

            task = t_repo.get_by_id(db, task_id)

            updated_fields: list[str] = []

            if status is not None:
                task.status = status
                updated_fields.append("status")

            if priority is not None:
                task.priority = priority
                updated_fields.append("priority")

            if due_date is not None:
                try:
                    due_date_dt = datetime.datetime.fromisoformat(
                        due_date.replace("Z", "+00:00")
                    )
                except ValueError:
                    raise ToolError(
                        f"Invalid due_date format: {due_date}. Use ISO 8601."
                    )
                task.due_date = due_date_dt
                updated_fields.append("due_date")

            if notion_id is not None:
                task.notion_id = notion_id
                updated_fields.append("notion_id")

            if name is not None:
                task.name = sec.scrub(name).clean
                updated_fields.append("name")

            if source_url is not None:
                task.source_url = source_url
                updated_fields.append("source_url")

            db.add(task)
            db.flush()

            task_state_updated = False
            if "status" in updated_fields:
                if task.id is None:
                    raise ToolError("Internal error: task was not assigned an id after flush")
                t_state_repo.on_status_changed(db, task.id)
                task_state_updated = True

            if status == TaskStatus.DONE and task.notion_id:
                try:
                    result = await ctx.elicit(
                        "Task closed. What was the outcome? (1-2 sentences, or press Enter to skip)",
                        response_type=str,
                    )
                    if isinstance(result, AcceptedElicitation) and result.data:
                        scrubbed_outcome = sec.scrub(result.data).clean
                        wb.append_task_outcome(task, scrubbed_outcome)
                except Exception as e:
                    logger.debug("ctx.elicit unavailable for task outcome: %s", e)

            status_writeback = None
            due_date_writeback = None
            priority_writeback = None

            if "status" in updated_fields:
                jira_wb = wb.push_task_status(task)
                notion_wb = wb.push_task_status_to_notion(task)
                status_writeback = WriteBackStatus(
                    ok=jira_wb.ok and notion_wb.ok,
                    error=", ".join(filter(None, [jira_wb.error, notion_wb.error])),
                    page_id=task.notion_id,
                )

            if "due_date" in updated_fields:
                due_date_writeback = wb.push_task_due_date(task)

            if "priority" in updated_fields:
                priority_writeback = wb.push_task_priority(task)

            return UpdateTaskResponse(
                task_id=task.id,
                updated_fields=updated_fields,
                status_writeback=status_writeback,
                due_date_writeback=due_date_writeback,
                priority_writeback=priority_writeback,
                task_state_updated=task_state_updated,
            )
    except ValueError as e:
        logger.warning("update_task failed: %s", e)
        raise ToolError(str(e)) from e


async def create_task(
    ctx: Context,
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
    sec: SecurityService = Depends(get_security),
    t_state_repo: TaskStateRepository = Depends(get_task_state_repo),
    wb: WriteBackService = Depends(get_writeback),
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    logger.info("create_task priority=%s category=%s", priority.value, category.value)
    with _helpers.get_session() as db:
        session_id: int | None = await ctx.get_state("current_session_id")
        await _log_tool_call(db, "create_task", session_id=session_id)
        clean_name = sec.scrub(name).clean
        task = Task(
            name=clean_name,
            priority=priority,
            category=category,
            status=TaskStatus.TODO,
            source_id=source_id,
            source_url=source_url,
        )
        db.add(task)
        db.flush()
        db.refresh(task)
        if task.id is None:
            raise ToolError("Internal error: task was not assigned an id after flush")

        t_state_repo.create_for_task(db, task)

        if meeting_id:
            db.add(MeetingTasks(meeting_id=meeting_id, task_id=task.id))

        wb_result = wb.push_task_to_notion(task)
        if wb_result.page_id:
            task.notion_id = wb_result.page_id
            db.flush()

        return CreateTaskResponse(
            task_id=task.id,
            notion_write_back=wb_result,
        )


async def rewind_task(
    ctx: Context,
    task_id: int,
    n_repo: NoteRepository = Depends(get_note_repo),
) -> RewindResponse:
    """Reconstruct the full note timeline for a task, oldest first."""
    logger.info("rewind_task task_id=%d", task_id)
    with _helpers.get_session() as db:
        session_id: int | None = await ctx.get_state("current_session_id")
        await _log_tool_call(db, "rewind_task", session_id=session_id)

        task = db.get(Task, task_id)
        if task is None:
            raise ToolError(f"Task {task_id} not found")

        task_state = db.get(TaskState, task_id)
        if task_state is None:
            raise ToolError(f"TaskState missing for task {task_id}")

        notes_desc = n_repo.get_for_task(
            db, task_id=task.id, source_id=task.source_id
        )
        # Filter persisted notes only (id is None only for unpersisted models; DB rows always have id)
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
    ctx: Context,
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
) -> MissingResponse:
    """Surface cognitive gaps for a task using seven diagnostic rules."""
    logger.info("what_am_i_missing task_id=%d", task_id)
    with _helpers.get_session() as db:
        session_id: int | None = await ctx.get_state("current_session_id")
        await _log_tool_call(db, "what_am_i_missing", session_id=session_id)
        try:
            task = t_repo.get_by_id(db, task_id)
        except ValueError as e:
            raise ToolError(str(e)) from e
        task_state = db.get(TaskState, task_id)
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

        signals.sort(key=lambda s: _SEVERITY_ORDER[s.severity])
        return MissingResponse(signals=signals)


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(task_start)
mcp.tool()(save_note)
mcp.tool()(update_task)
mcp.tool()(create_task)
mcp.tool()(rewind_task)
mcp.tool()(what_am_i_missing)
