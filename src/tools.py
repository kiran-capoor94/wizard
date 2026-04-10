import logging

from fastmcp import Context
from fastmcp.server.dependencies import CurrentContext
from sqlmodel import select

from .database import get_session
from .schemas import (
    CreateTaskResponse,
    GetMeetingResponse,
    IngestMeetingResponse,
    SaveMeetingSummaryResponse,
    SaveNoteResponse,
    SessionEndResponse,
    SessionStartResponse,
    TaskStartResponse,
    UpdateTaskStatusResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy dependency singletons — cached for process lifetime.
# Shared clients are created once and passed to both SyncService and
# WriteBackService so there is exactly one JiraClient, one NotionClient,
# and one SecurityService per process.
# Config changes require restart.
# ---------------------------------------------------------------------------

_jira_inst = None
_notion_inst = None
_security_svc = None
_sync_svc = None
_wb_svc = None
_task_repo_inst = None
_meeting_repo_inst = None
_note_repo_inst = None


def _jira_client():
    global _jira_inst
    if _jira_inst is None:
        from .config import settings
        from .integrations import JiraClient

        _jira_inst = JiraClient(
            base_url=settings.jira.base_url,
            token=settings.jira.token,
            project_key=settings.jira.project_key,
        )
    return _jira_inst


def _notion_client():
    global _notion_inst
    if _notion_inst is None:
        from .config import settings
        from .integrations import NotionClient

        _notion_inst = NotionClient(
            token=settings.notion.token,
            daily_page_id=settings.notion.daily_page_id,
            tasks_db_id=settings.notion.tasks_db_id,
            meetings_db_id=settings.notion.meetings_db_id,
        )
    return _notion_inst


def _security():
    global _security_svc
    if _security_svc is None:
        from .config import settings
        from .security import SecurityService

        _security_svc = SecurityService(
            allowlist=settings.scrubbing.allowlist,
            enabled=settings.scrubbing.enabled,
        )
    return _security_svc


def _sync_service():
    global _sync_svc
    if _sync_svc is None:
        from .services import SyncService

        _sync_svc = SyncService(
            jira=_jira_client(), notion=_notion_client(), security=_security()
        )
    return _sync_svc


def _writeback():
    global _wb_svc
    if _wb_svc is None:
        from .services import WriteBackService

        _wb_svc = WriteBackService(jira=_jira_client(), notion=_notion_client())
    return _wb_svc


def _task_repo():
    global _task_repo_inst
    if _task_repo_inst is None:
        from .repositories import TaskRepository

        _task_repo_inst = TaskRepository()
    return _task_repo_inst


def _meeting_repo():
    global _meeting_repo_inst
    if _meeting_repo_inst is None:
        from .repositories import MeetingRepository

        _meeting_repo_inst = MeetingRepository()
    return _meeting_repo_inst


def _note_repo():
    global _note_repo_inst
    if _note_repo_inst is None:
        from .repositories import NoteRepository

        _note_repo_inst = NoteRepository()
    return _note_repo_inst


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def session_start(ctx: Context = CurrentContext()) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    from .models import WizardSession

    with get_session() as db:
        ctx.info("Creating new session")
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        ctx.report_progress(1, 3)
        ctx.info("Syncing integrations")
        sync_results = _sync_service().sync_all(db)
        ctx.report_progress(2, 3)

        ctx.report_progress(3, 3)
        return SessionStartResponse(
            session_id=session.id,
            open_tasks=_task_repo().get_open_task_contexts(db),
            blocked_tasks=_task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=_meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
        )


def task_start(task_id: int) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context."""
    from .schemas import NoteDetail

    with get_session() as db:
        task = _task_repo().get_by_id(db, task_id)
        task_ctx = _task_repo().build_task_context(db, task)

        notes = _note_repo().get_for_task(db, task_id=task.id, source_id=task.source_id)
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


def save_note(task_id: int, note_type: str, content: str) -> SaveNoteResponse:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    from .models import Note, NoteType

    with get_session() as db:
        task = _task_repo().get_by_id(db, task_id)
        clean = _security().scrub(content).clean
        note = Note(
            note_type=NoteType(note_type),
            content=clean,
            task_id=task.id,
            source_id=task.source_id,
        )
        saved = _note_repo().save(db, note)
        assert saved.id is not None
        return SaveNoteResponse(note_id=saved.id)


def update_task_status(task_id: int, new_status: str) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back. Always commits local state first."""
    from .models import TaskStatus

    with get_session() as db:
        task = _task_repo().get_by_id(db, task_id)
        task.status = TaskStatus(new_status)
        db.add(task)
        db.flush()
        db.refresh(task)
        assert task.id is not None

        jira_wb = _writeback().push_task_status(task)
        notion_wb = _writeback().push_task_status_to_notion(task)

        return UpdateTaskStatusResponse(
            task_id=task.id,
            new_status=task.status,
            jira_write_back=jira_wb,
            notion_write_back=notion_wb,
        )


def get_meeting(meeting_id: int) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks. Check already_summarised before calling save_meeting_summary."""
    from .models import TaskStatus

    with get_session() as db:
        meeting = _meeting_repo().get_by_id(db, meeting_id)
        assert meeting.id is not None

        linked_tasks = [
            _task_repo().build_task_context(db, t)
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
    from .models import MeetingTasks, Note, NoteType

    with get_session() as db:
        meeting = _meeting_repo().get_by_id(db, meeting_id)
        assert meeting.id is not None

        clean_summary = _security().scrub(summary).clean
        meeting.summary = clean_summary
        db.add(meeting)

        note = Note(
            note_type=NoteType.DOCS,
            content=clean_summary,
            meeting_id=meeting.id,
            session_id=session_id,
        )
        saved = _note_repo().save(db, note)
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
        wb_result = _writeback().push_meeting_summary(meeting)

        linked_task_ids = [t.id for t in meeting.tasks if t.id is not None]

        return SaveMeetingSummaryResponse(
            note_id=saved.id,
            linked_task_ids=linked_task_ids,
            notion_write_back=wb_result,
        )


def session_end(session_id: int, summary: str, ctx: Context = CurrentContext()) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    from .models import WizardSession, Note, NoteType

    with get_session() as db:
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        ctx.info("Saving session summary")
        clean_summary = _security().scrub(summary).clean
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
        saved = _note_repo().save(db, note)
        assert saved.id is not None

        ctx.info("Writing back to Notion")
        wb_result = _writeback().push_session_summary(session)

        return SessionEndResponse(
            note_id=saved.id,
            notion_write_back=wb_result,
        )


def ingest_meeting(
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: str = "general",
    ctx: Context = CurrentContext(),
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    from .models import Meeting, MeetingCategory

    valid_categories = [c.value for c in MeetingCategory]
    if category not in valid_categories:
        raise ValueError(f"Invalid category '{category}'. Valid: {valid_categories}")

    with get_session() as db:
        ctx.info("Scrubbing and storing meeting")
        clean_title = _security().scrub(title).clean
        clean_content = _security().scrub(content).clean

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
                category=MeetingCategory(category),
            )
            db.add(meeting)

        db.flush()
        db.refresh(meeting)
        assert meeting.id is not None

        ctx.info("Writing back to Notion")
        wb_result = _writeback().push_meeting_to_notion(meeting)
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
    priority: str = "medium",
    category: str = "issue",
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
    ctx: Context = CurrentContext(),
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    from .models import Task, TaskPriority, TaskCategory, TaskStatus, MeetingTasks

    valid_priorities = [p.value for p in TaskPriority]
    if priority not in valid_priorities:
        raise ValueError(f"Invalid priority '{priority}'. Valid: {valid_priorities}")
    valid_categories = [c.value for c in TaskCategory]
    if category not in valid_categories:
        raise ValueError(f"Invalid category '{category}'. Valid: {valid_categories}")

    with get_session() as db:
        ctx.info("Creating task")
        clean_name = _security().scrub(name).clean
        task = Task(
            name=clean_name,
            priority=TaskPriority(priority),
            category=TaskCategory(category),
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
        wb_result = _writeback().push_task_to_notion(task)
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


def _get_mcp():
    from .mcp_instance import mcp

    return mcp


_mcp = _get_mcp()
_mcp.tool()(session_start)
_mcp.tool()(task_start)
_mcp.tool()(save_note)
_mcp.tool()(update_task_status)
_mcp.tool()(get_meeting)
_mcp.tool()(save_meeting_summary)
_mcp.tool()(session_end)
_mcp.tool()(ingest_meeting)
_mcp.tool()(create_task)
