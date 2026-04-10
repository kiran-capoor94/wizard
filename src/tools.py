import logging

from fastmcp.exceptions import ToolError
from sqlmodel import select

from .database import get_session
from .deps import meeting_repo, note_repo, security, sync_service, task_repo, writeback
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
    TaskStartResponse,
    UpdateTaskStatusResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def session_start() -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        sync_results = sync_service().sync_all(db)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
        )


def task_start(task_id: int) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context."""
    logger.info("task_start task_id=%d", task_id)
    try:
        with get_session() as db:
            task = task_repo().get_by_id(db, task_id)
            task_ctx = task_repo().build_task_context(db, task)

            notes = note_repo().get_for_task(db, task_id=task.id, source_id=task.source_id)
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


def save_note(task_id: int, note_type: NoteType, content: str) -> SaveNoteResponse:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)
    try:
        with get_session() as db:
            task = task_repo().get_by_id(db, task_id)
            clean = security().scrub(content).clean
            note = Note(
                note_type=note_type,
                content=clean,
                task_id=task.id,
                source_id=task.source_id,
            )
            saved = note_repo().save(db, note)
            assert saved.id is not None
            return SaveNoteResponse(note_id=saved.id)
    except ValueError as e:
        logger.warning("save_note failed: %s", e)
        raise ToolError(str(e)) from e


def update_task_status(
    task_id: int, new_status: TaskStatus
) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back."""
    logger.info("update_task_status task_id=%d new_status=%s", task_id, new_status.value)
    try:
        with get_session() as db:
            task = task_repo().get_by_id(db, task_id)
            task.status = new_status
            db.add(task)
            db.flush()
            db.refresh(task)
            assert task.id is not None

            jira_wb = writeback().push_task_status(task)
            notion_wb = writeback().push_task_status_to_notion(task)

            return UpdateTaskStatusResponse(
                task_id=task.id,
                new_status=task.status,
                jira_write_back=jira_wb,
                notion_write_back=notion_wb,
            )
    except ValueError as e:
        logger.warning("update_task_status failed: %s", e)
        raise ToolError(str(e)) from e


def get_meeting(meeting_id: int) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks."""
    logger.info("get_meeting meeting_id=%d", meeting_id)
    try:
        with get_session() as db:
            meeting = meeting_repo().get_by_id(db, meeting_id)
            assert meeting.id is not None

            linked_tasks = [
                task_repo().build_task_context(db, t)
                for t in meeting.tasks
                if t.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
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


def save_meeting_summary(
    meeting_id: int, session_id: int, summary: str, task_ids: list[int] | None = None
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
    logger.info("save_meeting_summary meeting_id=%d session_id=%d", meeting_id, session_id)
    try:
        with get_session() as db:
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


def session_end(session_id: int, summary: str) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    logger.info("session_end session_id=%d", session_id)
    with get_session() as db:
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

        return SessionEndResponse(
            note_id=saved.id,
            notion_write_back=wb_result,
        )


def ingest_meeting(
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    logger.info("ingest_meeting source_id=%s", source_id)
    with get_session() as db:
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


def create_task(
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
