import logging
from typing import Literal

from fastmcp import Context
from fastmcp.exceptions import ToolError
from sqlmodel import Session, select

from .database import get_session
from .deps import (
    meeting_repo,
    note_repo,
    notion_client,
    security,
    sync_service,
    task_repo,
    task_state_repo,
    writeback,
)
from .mcp_instance import mcp
from .models import (
    Meeting,
    MeetingCategory,
    MeetingTasks,
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskStatus,
    ToolCall,
    WizardSession,
)
from .schemas import (
    CreateTaskResponse,
    GetMeetingResponse,
    IngestMeetingResponse,
    NoteDetail,
    SaveMeetingSummaryResponse,
    SaveNoteResponse,
    SessionEndResponse,
    SessionStartResponse,
    SessionState,
    SourceSyncStatus,
    TaskStartResponse,
    UpdateTaskStatusResponse,
)

logger = logging.getLogger(__name__)


async def _log_tool_call(db: Session, tool_name: str, session_id: int | None = None) -> None:
    db.add(ToolCall(tool_name=tool_name, session_id=session_id))
    db.flush()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def session_start(ctx: Context) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None
        await _log_tool_call(db, "session_start", session_id=session.id)

        svc = sync_service()
        sync_results: list[SourceSyncStatus] = []
        sync_steps = [
            ("jira", svc.sync_jira, "Syncing Jira..."),
            ("notion_tasks", svc.sync_notion_tasks, "Syncing Notion tasks..."),
            ("notion_meetings", svc.sync_notion_meetings, "Syncing Notion meetings..."),
        ]
        for i, (source, fn, label) in enumerate(sync_steps):
            await ctx.report_progress(i, 3, label)
            try:
                fn(db)
                sync_results.append(SourceSyncStatus(source=source, ok=True))
            except Exception as e:
                logger.warning("Sync failed for %s: %s", source, e)
                sync_results.append(SourceSyncStatus(source=source, ok=False, error=str(e)))
        await ctx.report_progress(3, 3, "Sync complete.")

        await ctx.set_state("current_session_id", session.id)
        await ctx.info(f"Session {session.id} started.")

        daily_page = None
        try:
            daily_page = notion_client().ensure_daily_page()
            session.daily_page_id = daily_page.page_id
            db.add(session)
            db.flush()
        except Exception as e:
            logger.warning("ensure_daily_page failed: %s", e)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
            daily_page=daily_page,
        )


async def task_start(ctx: Context, task_id: int) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context.

    task_id: integer task ID from the open_tasks or blocked_tasks list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("task_start task_id=%d", task_id)
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "task_start", session_id=session_id)
            task = task_repo().get_by_id(db, task_id)
            task_ctx = task_repo().build_task_context(db, task)

            notes = note_repo().get_for_task(
                db, task_id=task.id, source_id=task.source_id
            )
            notes_by_type: dict[str, int] = {}
            for note in notes:
                key = note.note_type.value
                notes_by_type[key] = notes_by_type.get(key, 0) + 1

            prior_notes = [NoteDetail.from_model(n) for n in notes]

            return TaskStartResponse(
                task=task_ctx,
                compounding=len(notes) > 0,
                notes_by_type=notes_by_type,
                prior_notes=prior_notes,
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
) -> SaveNoteResponse:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "save_note", session_id=session_id)
            task = task_repo().get_by_id(db, task_id)
            if note_type in (NoteType.INVESTIGATION, NoteType.DECISION) and mental_model is None:
                try:
                    from fastmcp.server.elicitation import AcceptedElicitation
                    result = await ctx.elicit(
                        "Optional: summarise what you now understand in 1-2 sentences (mental model). "
                        "Press Enter to skip.",
                        response_type=str,
                    )
                    if isinstance(result, AcceptedElicitation) and result.data:
                        mental_model = result.data
                except Exception as e:
                    logger.debug("ctx.elicit unavailable for mental_model: %s", e)
            clean = security().scrub(content).clean
            note = Note(
                note_type=note_type,
                content=clean,
                mental_model=mental_model,
                task_id=task.id,
                source_id=task.source_id,
                source_type=task.source_type,
                session_id=session_id,
            )
            saved = note_repo().save(db, note)
            assert saved.id is not None
            task_state_repo().on_note_saved(db, task_id)
            return SaveNoteResponse(note_id=saved.id, mental_model=saved.mental_model)
    except ValueError as e:
        logger.warning("save_note failed: %s", e)
        raise ToolError(str(e)) from e


async def update_task_status(
    ctx: Context, task_id: int, new_status: TaskStatus
) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back."""
    logger.info(
        "update_task_status task_id=%d new_status=%s", task_id, new_status.value
    )
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "update_task_status", session_id=session_id)
            task = task_repo().get_by_id(db, task_id)
            task.status = new_status
            db.add(task)
            db.flush()
            db.refresh(task)
            assert task.id is not None

            task_state_repo().on_status_changed(db, task.id)

            if new_status == TaskStatus.DONE:
                try:
                    from fastmcp.server.elicitation import AcceptedElicitation
                    elicit_result = await ctx.elicit(
                        "Task closed. What was the outcome? (1-2 sentences, or press Enter to skip)",
                        response_type=str,
                    )
                    if isinstance(elicit_result, AcceptedElicitation) and elicit_result.data:
                        scrubbed_outcome = security().scrub(elicit_result.data).clean
                        if task.notion_id:
                            writeback().append_task_outcome(task, scrubbed_outcome)
                        else:
                            logger.info(
                                "Task %d done with outcome but no notion_id; skipping notion append",
                                task.id,
                            )
                except Exception as e:
                    logger.debug("ctx.elicit unavailable for task outcome: %s", e)

            jira_wb = writeback().push_task_status(task)
            notion_wb = writeback().push_task_status_to_notion(task)

            return UpdateTaskStatusResponse(
                task_id=task.id,
                new_status=task.status,
                jira_write_back=jira_wb,
                notion_write_back=notion_wb,
                task_state_updated=True,
            )
    except ValueError as e:
        logger.warning("update_task_status failed: %s", e)
        raise ToolError(str(e)) from e


async def get_meeting(ctx: Context, meeting_id: int) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks.

    meeting_id: integer meeting ID from the unsummarised_meetings list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("get_meeting meeting_id=%d", meeting_id)
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "get_meeting", session_id=session_id)
            meeting = meeting_repo().get_by_id(db, meeting_id)
            assert meeting.id is not None

            linked_tasks = [
                task_repo().build_task_context(db, t)
                for t in meeting.tasks
                if t.status
                in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
            ]

            return GetMeetingResponse(
                meeting_id=meeting.id,
                title=meeting.title,
                category=meeting.category,
                content=meeting.content,
                already_summarised=meeting.summary is not None,
                existing_summary=meeting.summary,
                open_tasks=linked_tasks,
            )
    except ValueError as e:
        logger.warning("get_meeting failed: %s", e)
        raise ToolError(str(e)) from e


async def save_meeting_summary(
    ctx: Context,
    meeting_id: int,
    session_id: int,
    summary: str,
    task_ids: list[int] | None = None,
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
    logger.info(
        "save_meeting_summary meeting_id=%d session_id=%d", meeting_id, session_id
    )
    try:
        with get_session() as db:
            await _log_tool_call(db, "save_meeting_summary", session_id=session_id)
            meeting = meeting_repo().get_by_id(db, meeting_id)
            assert meeting.id is not None

            clean_summary = security().scrub(summary).clean
            meeting.summary = clean_summary
            db.add(meeting)

            note = Note(
                note_type=NoteType.DOCS,
                content=clean_summary,
                meeting_id=meeting.id,
                session_id=session_id,
            )
            saved = note_repo().save(db, note)
            assert saved.id is not None

            if task_ids:
                for tid in task_ids:
                    existing_link = db.exec(
                        select(MeetingTasks).where(
                            MeetingTasks.meeting_id == meeting.id,
                            MeetingTasks.task_id == tid,
                        )
                    ).first()
                    if not existing_link:
                        db.add(MeetingTasks(meeting_id=meeting.id, task_id=tid))

            db.flush()
            wb_result = writeback().push_meeting_summary(meeting)

            linked_task_ids = [t.id for t in meeting.tasks if t.id is not None]

            return SaveMeetingSummaryResponse(
                note_id=saved.id,
                linked_task_ids=linked_task_ids,
                notion_write_back=wb_result,
            )
    except ValueError as e:
        logger.warning("save_meeting_summary failed: %s", e)
        raise ToolError(str(e)) from e


async def session_end(ctx: Context, session_id: int, summary: str) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    logger.info("session_end session_id=%d", session_id)
    with get_session() as db:
        await _log_tool_call(db, "session_end", session_id=session_id)
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ToolError(f"Session {session_id} not found")

        clean_summary = security().scrub(summary).clean
        session.summary = clean_summary
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary,
            session_id=session.id,
        )
        saved = note_repo().save(db, note)
        assert saved.id is not None

        wb_result = writeback().push_session_summary(session)

        await ctx.delete_state("current_session_id")
        return SessionEndResponse(
            note_id=saved.id,
            notion_write_back=wb_result,
        )


async def ingest_meeting(
    ctx: Context,
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    logger.info("ingest_meeting source_id=%s", source_id)
    with get_session() as db:
        await _log_tool_call(db, "ingest_meeting")
        clean_title = security().scrub(title).clean
        clean_content = security().scrub(content).clean

        meeting: Meeting | None = None
        already_existed = False
        if source_id:
            meeting = db.exec(
                select(Meeting).where(Meeting.source_id == source_id)
            ).first()
        if meeting:
            already_existed = True
            meeting.title = clean_title
            meeting.content = clean_content
            db.add(meeting)
        else:
            meeting = Meeting(
                title=clean_title,
                content=clean_content,
                source_id=source_id,
                source_type="KRISP" if source_id else None,
                source_url=source_url,
                category=category,
            )
            db.add(meeting)

        db.flush()
        db.refresh(meeting)
        assert meeting.id is not None

        wb_result = writeback().push_meeting_to_notion(meeting)
        if wb_result.page_id:
            meeting.notion_id = wb_result.page_id
            db.flush()

        return IngestMeetingResponse(
            meeting_id=meeting.id,
            already_existed=already_existed,
            notion_write_back=wb_result,
        )


async def create_task(
    ctx: Context,
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    logger.info("create_task priority=%s category=%s", priority.value, category.value)
    with get_session() as db:
        await _log_tool_call(db, "create_task")
        clean_name = security().scrub(name).clean
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
        assert task.id is not None

        task_state_repo().create_for_task(db, task)

        if meeting_id:
            db.add(MeetingTasks(meeting_id=meeting_id, task_id=task.id))

        wb_result = writeback().push_task_to_notion(task)
        if wb_result.page_id:
            task.notion_id = wb_result.page_id
            db.flush()

        return CreateTaskResponse(
            task_id=task.id,
            notion_write_back=wb_result,
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(session_start)
mcp.tool()(task_start)
mcp.tool()(save_note)
mcp.tool()(update_task_status)
mcp.tool()(get_meeting)
mcp.tool()(save_meeting_summary)
mcp.tool()(session_end)
mcp.tool()(ingest_meeting)
mcp.tool()(create_task)
