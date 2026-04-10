import logging
from sqlmodel import Session, select
from .schemas import (
    SaveNoteResponse,
    UpdateTaskStatusResponse,
    GetMeetingResponse,
    SaveMeetingSummaryResponse,
    SessionEndResponse,
)

logger = logging.getLogger(__name__)

_cached_deps = None


def _get_db() -> Session:
    from .database import engine

    return Session(engine)


def _get_deps():
    global _cached_deps
    if _cached_deps is None:
        from .config import settings
        from .integrations import JiraClient, NotionClient
        from .security import SecurityService
        from .services import SyncService, WriteBackService
        from .repositories import NoteRepository

        jira = JiraClient(
            base_url=settings.jira.base_url,
            token=settings.jira.token,
            project_key=settings.jira.project_key,
        )
        notion = NotionClient(
            token=settings.notion.token,
            daily_page_id=settings.notion.daily_page_id,
            tasks_db_id=settings.notion.tasks_db_id,
            meetings_db_id=settings.notion.meetings_db_id,
        )
        security = SecurityService(
            allowlist=settings.scrubbing.allowlist, enabled=settings.scrubbing.enabled
        )
        sync = SyncService(jira=jira, notion=notion, security=security)
        writeback = WriteBackService(jira=jira, notion=notion)
        repo = NoteRepository()
        _cached_deps = (sync, writeback, repo, security)
    return _cached_deps


def _build_task_context(task, repo, db):
    from .schemas import TaskContext

    latest = repo.get_latest_for_task(db, task_id=task.id, source_id=task.source_id)
    return TaskContext(
        id=task.id,
        name=task.name,
        status=task.status,
        priority=task.priority,
        category=task.category,
        due_date=task.due_date,
        source_id=task.source_id,
        source_url=task.source_url,
        last_note_type=latest.note_type if latest else None,
        last_note_preview=latest.content[:300] if latest else None,
        last_worked_at=latest.created_at if latest else None,
    )


def _sort_tasks(tasks):
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        tasks,
        key=lambda t: (
            priority_order.get(t.priority.value, 99),
            -(t.last_worked_at.timestamp() if t.last_worked_at else 0),
        ),
    )


def _get_mcp():
    from .mcp_instance import mcp

    return mcp


def session_start() -> dict:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    from .models import Meeting, Task, TaskStatus, WizardSession
    from .schemas import SessionStartResponse, MeetingContext

    sync, wb, repo, security = _get_deps()
    db = _get_db()
    try:
        session = WizardSession()
        db.add(session)
        db.commit()
        db.refresh(session)

        sync.sync_all(db)

        open_tasks_raw = list(
            db.exec(
                select(Task).where(
                    Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS])
                )
            ).all()
        )
        blocked_tasks_raw = list(
            db.exec(select(Task).where(Task.status == TaskStatus.BLOCKED)).all()
        )
        unsummarised_raw = list(
            db.exec(select(Meeting).where(Meeting.summary == None)).all()
        )

        open_tasks = _sort_tasks(
            [_build_task_context(t, repo, db) for t in open_tasks_raw]
        )
        blocked_tasks = _sort_tasks(
            [_build_task_context(t, repo, db) for t in blocked_tasks_raw]
        )
        unsummarised = [
            MeetingContext(
                id=m.id,
                title=m.title,
                category=m.category,
                created_at=m.created_at,
                has_summary=False,
            )
            for m in unsummarised_raw
        ]

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=open_tasks,
            blocked_tasks=blocked_tasks,
            unsummarised_meetings=unsummarised,
        ).model_dump(mode="json")
    finally:
        db.close()


def task_start(task_id: int) -> dict:
    """Returns full task context + all prior notes for compounding context."""
    from .models import Task
    from .schemas import TaskContext, TaskStartResponse, NoteDetail

    _sync, _wb, repo, _security = _get_deps()
    db = _get_db()
    try:
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        notes = repo.get_for_task(db, task_id=task.id, source_id=task.source_id)
        latest = notes[-1] if notes else None

        task_ctx = TaskContext(
            id=task.id,
            name=task.name,
            status=task.status,
            priority=task.priority,
            category=task.category,
            due_date=task.due_date,
            source_id=task.source_id,
            source_url=task.source_url,
            last_note_type=latest.note_type if latest else None,
            last_note_preview=latest.content[:300] if latest else None,
            last_worked_at=latest.created_at if latest else None,
        )

        notes_by_type: dict[str, int] = {}
        for note in notes:
            key = note.note_type.value
            notes_by_type[key] = notes_by_type.get(key, 0) + 1

        prior_notes = [
            NoteDetail(
                id=n.id,
                note_type=n.note_type,
                content=n.content,
                created_at=n.created_at,
                source_id=n.source_id,
            )
            for n in notes
        ]

        return TaskStartResponse(
            task=task_ctx,
            compounding=len(notes) > 0,
            notes_by_type=notes_by_type,
            prior_notes=prior_notes,
        ).model_dump(mode="json")
    finally:
        db.close()


def save_note(task_id: int, note_type: str, content: str) -> dict:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    from .models import Note, NoteType, Task

    _sync, _wb, repo, security = _get_deps()
    db = _get_db()
    try:
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        clean = security.scrub(content).clean
        note = Note(
            note_type=NoteType(note_type),
            content=clean,
            task_id=task.id,
            source_id=task.source_id,
        )
        saved = repo.save(db, note)
        return SaveNoteResponse(note_id=saved.id).model_dump(mode="json")
    finally:
        db.close()


def update_task_status(task_id: int, new_status: str) -> dict:
    """Updates task status locally and attempts Jira and Notion write-back. Always commits local state first."""
    from .models import Task, TaskStatus

    _sync, wb, _repo, _security = _get_deps()
    db = _get_db()
    try:
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        task.status = TaskStatus(new_status)
        db.add(task)
        db.commit()
        db.refresh(task)

        jira_ok = wb.push_task_status(task)
        notion_ok = wb.push_task_status_to_notion(task)

        return UpdateTaskStatusResponse(
            task_id=task.id,
            new_status=task.status,
            write_back_succeeded=jira_ok,
            notion_write_back_succeeded=notion_ok,
        ).model_dump(mode="json")
    finally:
        db.close()


def get_meeting(meeting_id: int) -> dict:
    """Returns meeting transcript and linked open tasks. Check already_summarised before calling save_meeting_summary."""
    from .models import Meeting, TaskStatus

    _sync, _wb, repo, _security = _get_deps()
    db = _get_db()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            raise ValueError(f"Meeting {meeting_id} not found")

        linked_tasks = [
            _build_task_context(t, repo, db)
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
        ).model_dump(mode="json")
    finally:
        db.close()


def save_meeting_summary(
    meeting_id: int, session_id: int, summary: str, task_ids: list[int] | None = None
) -> dict:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
    from .models import Meeting, Note, NoteType

    _sync, wb, repo, security = _get_deps()
    db = _get_db()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            raise ValueError(f"Meeting {meeting_id} not found")

        clean_summary = security.scrub(summary).clean
        meeting.summary = clean_summary
        db.add(meeting)
        db.commit()
        db.refresh(meeting)

        note = Note(
            note_type=NoteType.DOCS,
            content=clean_summary,
            meeting_id=meeting.id,
            session_id=session_id,
        )
        saved = repo.save(db, note)

        # Link specified tasks to this meeting
        if task_ids:
            from .models import MeetingTasks

            for tid in task_ids:
                existing_link = db.exec(
                    select(MeetingTasks).where(
                        MeetingTasks.meeting_id == meeting.id,
                        MeetingTasks.task_id == tid,
                    )
                ).first()
                if not existing_link:
                    db.add(MeetingTasks(meeting_id=meeting.id, task_id=tid))
            db.commit()

        wb.push_meeting_summary(meeting)

        linked_task_ids = [t.id for t in meeting.tasks]

        return SaveMeetingSummaryResponse(
            note_id=saved.id,
            linked_task_ids=linked_task_ids,
        ).model_dump(mode="json")
    finally:
        db.close()


def session_end(session_id: int, summary: str) -> dict:
    """Persists session summary note and attempts Notion daily page write-back."""
    from .models import WizardSession, Note, NoteType

    _sync, wb, repo, security = _get_deps()
    db = _get_db()
    try:
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        clean_summary = security.scrub(summary).clean
        session.summary = clean_summary
        db.add(session)
        db.commit()
        db.refresh(session)

        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary,
            session_id=session.id,
        )
        saved = repo.save(db, note)

        wb.push_session_summary(session)

        return SessionEndResponse(note_id=saved.id).model_dump(mode="json")
    finally:
        db.close()


def ingest_meeting(
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: str = "general",
) -> dict:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    from .models import Meeting, MeetingCategory
    from .schemas import IngestMeetingResponse

    _sync, wb, _repo, security = _get_deps()
    db = _get_db()
    try:
        clean_title = security.scrub(title).clean
        clean_content = security.scrub(content).clean
        already_existed = False
        meeting = None
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
        db.commit()
        db.refresh(meeting)
        wb.push_meeting_to_notion(meeting)
        db.commit()
        return IngestMeetingResponse(
            meeting_id=meeting.id,
            already_existed=already_existed,
        ).model_dump(mode="json")
    finally:
        db.close()


def create_task(
    name: str,
    priority: str = "medium",
    category: str = "issue",
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
) -> dict:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    from .models import Task, TaskPriority, TaskCategory, TaskStatus, MeetingTasks
    from .schemas import CreateTaskResponse

    _sync, wb, _repo, security = _get_deps()
    db = _get_db()
    try:
        clean_name = security.scrub(name).clean
        task = Task(
            name=clean_name,
            priority=TaskPriority(priority),
            category=TaskCategory(category),
            status=TaskStatus.TODO,
            source_id=source_id,
            source_url=source_url,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        if meeting_id:
            link = MeetingTasks(meeting_id=meeting_id, task_id=task.id)
            db.add(link)
            db.commit()
        notion_ok = wb.push_task_to_notion(task)
        db.commit()
        return CreateTaskResponse(
            task_id=task.id,
            notion_write_back_succeeded=notion_ok,
        ).model_dump(mode="json")
    finally:
        db.close()


# Register tools with MCP
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
