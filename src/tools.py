import logging
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


def _get_db() -> Session:
    from .database import engine
    return Session(engine)


def _get_deps():
    from .config import settings
    from .integrations import JiraClient, KrispClient, NotionClient
    from .security import SecurityService
    from .services import SyncService, WriteBackService
    from .repositories import NoteRepository
    
    jira = JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
    )
    krisp = KrispClient(
        api_base_url=settings.krisp.api_base_url,
        token=settings.krisp.token,
    )
    notion = NotionClient(
        daily_page_id=settings.notion.daily_page_id,
        token=settings.notion.token,
    )
    security = SecurityService(allowlist=settings.scrubbing.allowlist)
    sync = SyncService(jira=jira, krisp=krisp, security=security)
    writeback = WriteBackService(jira=jira, notion=notion)
    repo = NoteRepository()
    return sync, writeback, repo, security


def _build_task_context(task, repo, db):
    from .models import NoteType
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
        last_note_preview=latest.content[:120] if latest else None,
        last_worked_at=latest.created_at if latest else None,
    )


def _sort_tasks(tasks):
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(tasks, key=lambda t: (priority_order.get(t.priority.value, 99), t.name))


def _get_mcp():
    from .mcp_instance import mcp
    return mcp


def session_start() -> dict:
    """Creates a session, syncs Jira and Krisp, returns open and blocked tasks + unsummarised meetings."""
    from .models import Meeting, Task, TaskStatus, WizardSession
    from .schemas import SessionStartResponse, MeetingContext
    
    sync, wb, repo, security = _get_deps()
    db = _get_db()
    session = WizardSession()
    db.add(session)
    db.commit()
    db.refresh(session)

    sync.sync_all(db)

    open_tasks_raw = list(db.exec(
        select(Task).where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
    ).all())
    blocked_tasks_raw = list(db.exec(
        select(Task).where(Task.status == TaskStatus.BLOCKED)
    ).all())
    unsummarised_raw = list(db.exec(
        select(Meeting).where(Meeting.summary == None)
    ).all())

    open_tasks = _sort_tasks([_build_task_context(t, repo, db) for t in open_tasks_raw])
    blocked_tasks = _sort_tasks([_build_task_context(t, repo, db) for t in blocked_tasks_raw])
    unsummarised = [
        MeetingContext(
            id=m.id, title=m.title, category=m.category,
            created_at=m.created_at, has_summary=False
        )
        for m in unsummarised_raw
    ]

    db.close()

    return SessionStartResponse(
        session_id=session.id,
        open_tasks=open_tasks,
        blocked_tasks=blocked_tasks,
        unsummarised_meetings=unsummarised,
    ).model_dump(mode="json")


def task_start(task_id: int) -> dict:
    """Returns full task context + all prior notes for compounding context."""
    from .models import Task
    from .schemas import TaskContext, TaskStartResponse, NoteDetail
    
    _sync, _wb, repo, _security = _get_deps()
    db = _get_db()
    task = db.get(Task, task_id)
    if task is None:
        db.close()
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
        last_note_preview=latest.content[:120] if latest else None,
        last_worked_at=latest.created_at if latest else None,
    )

    notes_by_type: dict[str, int] = {}
    for note in notes:
        key = note.note_type.value
        notes_by_type[key] = notes_by_type.get(key, 0) + 1

    prior_notes = [
        NoteDetail(
            id=n.id, note_type=n.note_type, content=n.content,
            created_at=n.created_at, source_id=n.source_id,
        )
        for n in notes
    ]

    db.close()

    return TaskStartResponse(
        task=task_ctx,
        compounding=len(notes) > 0,
        notes_by_type=notes_by_type,
        prior_notes=prior_notes,
    ).model_dump(mode="json")


# Register tools with MCP
_mcp = _get_mcp()
_mcp.tool()(session_start)
_mcp.tool()(task_start)
