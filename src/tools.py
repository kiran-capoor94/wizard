import logging
from functools import lru_cache

from fastmcp import Context
from fastmcp.server.dependencies import CurrentContext
from sqlmodel import select

from .config import settings
from .database import get_session
from .integrations import JiraClient, NotionClient
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
from .repositories import MeetingRepository, NoteRepository, TaskRepository
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
from .security import SecurityService
from .services import SyncService, WriteBackService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached dependency singletons — one instance per process.
# Tests call <func>.cache_clear() to reset.
# Config changes require restart.
# ---------------------------------------------------------------------------


@lru_cache
def jira_client() -> JiraClient:
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
    )


@lru_cache
def notion_client() -> NotionClient:
    return NotionClient(
        token=settings.notion.token,
        daily_page_id=settings.notion.daily_page_id,
        tasks_db_id=settings.notion.tasks_db_id,
        meetings_db_id=settings.notion.meetings_db_id,
    )


@lru_cache
def security() -> SecurityService:
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
    )


@lru_cache
def sync_service() -> SyncService:
    return SyncService(
        jira=jira_client(), notion=notion_client(), security=security()
    )


@lru_cache
def writeback() -> WriteBackService:
    return WriteBackService(jira=jira_client(), notion=notion_client())


@lru_cache
def task_repo() -> TaskRepository:
    return TaskRepository()


@lru_cache
def meeting_repo() -> MeetingRepository:
    return MeetingRepository()


@lru_cache
def note_repo() -> NoteRepository:
    return NoteRepository()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def session_start(ctx: Context = CurrentContext()) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    with get_session() as db:
        ctx.info("Creating new session")
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        ctx.report_progress(1, 3)
        ctx.info("Syncing integrations")
        sync_results = sync_service().sync_all(db)
        ctx.report_progress(2, 3)

        ctx.report_progress(3, 3)
        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
        )


def task_start(task_id: int) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context."""
    with get_session() as db:
        task = task_repo().get_by_id(db, task_id)
        task_ctx = task_repo().build_task_context(db, task)

        notes = note_repo().get_for_task(db, task_id=task.id, source_id=task.source_id)
        notes_by_type: dict[str, int] = {}
        for note in notes:
            key = note.note_type.value
            notes_by_type[key] = notes_by_type.get(key, 0) + 1

        prior_notes: list[NoteDetail] = []
        for n in notes:
            assert n.id is not None
            prior_notes.append(
                NoteDetail(
                    id=n.id,
                    note_type=n.note_type,
                    content=n.content,
                    created_at=n.created_at,
                    source_id=n.source_id,
                )
            )

        return TaskStartResponse(
            task=task_ctx,
            compounding=len(notes) > 0,
            notes_by_type=notes_by_type,
            prior_notes=prior_notes,
        )


def save_note(task_id: int, note_type: NoteType, content: str) -> SaveNoteResponse:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
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


def update_task_status(task_id: int, new_status: TaskStatus) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back."""
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


def get_meeting(meeting_id: int) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks."""
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


def save_meeting_summary(
    meeting_id: int, session_id: int, summary: str, task_ids: list[int] | None = None
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
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


def session_end(
    session_id: int, summary: str, ctx: Context = CurrentContext()
) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    with get_session() as db:
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        ctx.info("Saving session summary")
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

        ctx.info("Writing back to Notion")
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
    ctx: Context = CurrentContext(),
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    with get_session() as db:
        ctx.info("Scrubbing and storing meeting")
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

        ctx.info("Writing back to Notion")
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
    ctx: Context = CurrentContext(),
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    with get_session() as db:
        ctx.info("Creating task")
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

        ctx.info("Writing back to Notion")
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
