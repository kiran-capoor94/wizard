import json
import pytest
from unittest.mock import MagicMock, patch


def test_session_start_creates_session(db_session):
    from src.models import WizardSession
    from src.repositories import NoteRepository
    from src.services import SyncService, WriteBackService
    from src.security import SecurityService
    from src.tools import session_start

    # Monkey-patch the _get_deps and _get_db functions
    import src.tools
    sync_mock = MagicMock(spec=SyncService)
    sync_mock.sync_all.return_value = None
    src.tools._get_deps = lambda: (
        sync_mock,
        MagicMock(spec=WriteBackService),
        NoteRepository(),
        SecurityService(),
    )
    src.tools._get_db = lambda: db_session

    result = session_start()

    data = result if isinstance(result, dict) else json.loads(result)
    assert "session_id" in data
    assert "open_tasks" in data
    assert "blocked_tasks" in data
    assert "unsummarised_meetings" in data


def test_session_start_calls_sync(db_session):
    from src.models import WizardSession
    from src.repositories import NoteRepository
    from src.services import SyncService, WriteBackService
    from src.security import SecurityService
    from src.tools import session_start

    # Monkey-patch the _get_deps and _get_db functions
    import src.tools
    sync_mock = MagicMock(spec=SyncService)
    sync_mock.sync_all.return_value = None
    src.tools._get_deps = lambda: (
        sync_mock,
        MagicMock(spec=WriteBackService),
        NoteRepository(),
        SecurityService(),
    )
    src.tools._get_db = lambda: db_session

    session_start()

    sync_mock.sync_all.assert_called_once()


def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from src.models import Task, TaskStatus, Note, NoteType
    from src.repositories import NoteRepository
    from src.services import SyncService, WriteBackService
    from src.security import SecurityService
    from src.tools import task_start

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    prior_note = Note(note_type=NoteType.INVESTIGATION, content="prior investigation", task_id=task.id)
    db_session.add(prior_note)
    db_session.commit()
    db_session.refresh(prior_note)

    # Monkey-patch the _get_deps and _get_db functions
    import src.tools
    src.tools._get_deps = lambda: (
        MagicMock(spec=SyncService),
        MagicMock(spec=WriteBackService),
        NoteRepository(),
        SecurityService(),
    )
    src.tools._get_db = lambda: db_session

    result = task_start(task_id=task.id)

    data = result if isinstance(result, dict) else json.loads(result)
    assert data["compounding"] is True
    assert len(data["prior_notes"]) == 1


def test_task_start_returns_compounding_false_when_no_notes(db_session):
    from src.models import Task, TaskStatus
    from src.repositories import NoteRepository
    from src.services import SyncService, WriteBackService
    from src.security import SecurityService
    from src.tools import task_start

    task = Task(name="new task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    # Monkey-patch the _get_deps and _get_db functions
    import src.tools
    src.tools._get_deps = lambda: (
        MagicMock(spec=SyncService),
        MagicMock(spec=WriteBackService),
        NoteRepository(),
        SecurityService(),
    )
    src.tools._get_db = lambda: db_session

    result = task_start(task_id=task.id)

    data = result if isinstance(result, dict) else json.loads(result)
    assert data["compounding"] is False


def test_task_start_raises_when_task_not_found(db_session):
    from src.repositories import NoteRepository
    from src.services import SyncService, WriteBackService
    from src.security import SecurityService
    from src.tools import task_start

    # Monkey-patch the _get_deps and _get_db functions
    import src.tools
    src.tools._get_deps = lambda: (
        MagicMock(spec=SyncService),
        MagicMock(spec=WriteBackService),
        NoteRepository(),
        SecurityService(),
    )
    src.tools._get_db = lambda: db_session

    with pytest.raises(ValueError, match="Task 999 not found"):
        task_start(task_id=999)


def test_save_note_scrubs_and_persists(db_session):
    from src.tools import save_note
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Task

    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    repo = NoteRepository()
    security = SecurityService()

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    import src.tools
    src.tools._get_deps = lambda: (sync, wb, repo, security)
    src.tools._get_db = lambda: db_session

    result = save_note(
        task_id=task.id,
        note_type="investigation",
        content="john@example.com found a bug",
    )

    data = result if isinstance(result, dict) else json.loads(result)
    assert "note_id" in data

    from src.models import Note
    saved_note = db_session.get(Note, data["note_id"])
    assert "john@example.com" not in saved_note.content
    assert "[EMAIL_1]" in saved_note.content


def test_update_task_status_persists_and_writebacks(db_session):
    from src.tools import update_task_status
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Task, TaskStatus

    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    repo = NoteRepository()
    security = SecurityService()
    wb.push_task_status.return_value = True

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    task_id = task.id
    db_session.refresh(task)

    import src.tools
    src.tools._get_deps = lambda: (sync, wb, repo, security)
    src.tools._get_db = lambda: db_session

    result = update_task_status(task_id=task_id, new_status="done")

    data = result if isinstance(result, dict) else json.loads(result)
    assert data["new_status"] == "done"
    assert data["write_back_succeeded"] is True

    # Fetch fresh from DB after tool closes session
    task_fresh = db_session.get(Task, task_id)
    assert task_fresh.status == TaskStatus.DONE


def test_get_meeting_returns_content_and_open_tasks(db_session):
    from src.tools import get_meeting
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Task, TaskStatus, Meeting, MeetingTasks

    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    repo = NoteRepository()
    security = SecurityService()

    task = Task(name="fix auth", status=TaskStatus.IN_PROGRESS)
    meeting = Meeting(title="standup", content="we discussed fix auth")
    db_session.add(task)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(meeting)

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()

    import src.tools
    src.tools._get_deps = lambda: (sync, wb, repo, security)
    src.tools._get_db = lambda: db_session

    result = get_meeting(meeting_id=meeting.id)

    data = result if isinstance(result, dict) else json.loads(result)
    assert data["meeting_id"] == meeting.id
    assert data["already_summarised"] is False
    assert len(data["open_tasks"]) == 1


def test_save_meeting_summary_scrubs_and_persists(db_session):
    from src.tools import save_meeting_summary
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import WizardSession, Meeting, Note

    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    repo = NoteRepository()
    security = SecurityService()
    wb.push_meeting_summary.return_value = True

    session = WizardSession()
    meeting = Meeting(title="standup", content="notes")
    db_session.add(session)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(meeting)

    import src.tools
    src.tools._get_deps = lambda: (sync, wb, repo, security)
    src.tools._get_db = lambda: db_session

    result = save_meeting_summary(
        meeting_id=meeting.id,
        session_id=session.id,
        summary="patient 943 476 5919 was discussed",
    )

    data = result if isinstance(result, dict) else json.loads(result)
    assert "note_id" in data

    saved = db_session.get(Note, data["note_id"])
    assert "943 476 5919" not in saved.content
    assert "[NHS_ID_1]" in saved.content


def test_session_end_saves_summary_note(db_session):
    from src.tools import session_end
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import WizardSession, Note, NoteType

    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    repo = NoteRepository()
    security = SecurityService()
    wb.push_session_summary.return_value = True

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    session_id = session.id
    db_session.refresh(session)

    import src.tools
    src.tools._get_deps = lambda: (sync, wb, repo, security)
    src.tools._get_db = lambda: db_session

    result = session_end(
        session_id=session_id,
        summary="wrapped up today's work",
    )

    data = result if isinstance(result, dict) else json.loads(result)
    assert "note_id" in data

    saved = db_session.get(Note, data["note_id"])
    assert saved.note_type == NoteType.SESSION_SUMMARY
    assert saved.session_id == session_id


def test_task_start_closes_db_on_error(db_session):
    from src.tools import task_start
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    repo = NoteRepository()
    security = SecurityService()
    mock_db = MagicMock(wraps=db_session)
    mock_db.get.return_value = None
    with patch("src.tools._get_deps", return_value=(sync, wb, repo, security)):
        with patch("src.tools._get_db", return_value=mock_db):
            with pytest.raises(ValueError):
                task_start(task_id=999)
    mock_db.close.assert_called_once()


def test_update_task_status_dual_writeback(db_session):
    from src.tools import update_task_status
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Task, TaskStatus
    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    wb.push_task_status.return_value = True
    wb.push_task_status_to_notion.return_value = True
    repo = NoteRepository()
    security = SecurityService()
    task = Task(name="fix", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    with patch("src.tools._get_deps", return_value=(sync, wb, repo, security)):
        with patch("src.tools._get_db", return_value=db_session):
            result = update_task_status(task_id=task.id, new_status="done")
    data = result if isinstance(result, dict) else json.loads(result)
    assert data["write_back_succeeded"] is True
    assert data["notion_write_back_succeeded"] is True


def test_ingest_meeting_creates_meeting(db_session):
    from src.tools import ingest_meeting
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Meeting
    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    wb.push_meeting_to_notion.return_value = True
    repo = NoteRepository()
    security = SecurityService()
    with patch("src.tools._get_deps", return_value=(sync, wb, repo, security)):
        with patch("src.tools._get_db", return_value=db_session):
            result = ingest_meeting(
                title="Sprint Planning",
                content="john@example.com reported a bug",
                source_id="krisp-abc",
                source_url="https://krisp.ai/m/abc",
                category="planning",
            )
    data = result if isinstance(result, dict) else json.loads(result)
    assert "meeting_id" in data
    assert data["already_existed"] is False
    meeting = db_session.get(Meeting, data["meeting_id"])
    assert "john@example.com" not in meeting.content
    assert "[EMAIL_1]" in meeting.content


def test_ingest_meeting_dedup_by_source_id(db_session):
    from src.tools import ingest_meeting
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Meeting
    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    wb.push_meeting_to_notion.return_value = True
    repo = NoteRepository()
    security = SecurityService()
    existing = Meeting(title="Old", content="old", source_id="krisp-abc")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)
    with patch("src.tools._get_deps", return_value=(sync, wb, repo, security)):
        with patch("src.tools._get_db", return_value=db_session):
            result = ingest_meeting(title="New", content="new", source_id="krisp-abc")
    data = result if isinstance(result, dict) else json.loads(result)
    assert data["already_existed"] is True
    assert data["meeting_id"] == existing.id


def test_create_task_creates_and_links(db_session):
    from src.tools import create_task
    from src.services import SyncService, WriteBackService
    from src.repositories import NoteRepository
    from src.security import SecurityService
    from src.models import Meeting, Task, TaskStatus
    from sqlmodel import select
    sync = MagicMock(spec=SyncService)
    wb = MagicMock(spec=WriteBackService)
    wb.push_task_to_notion.return_value = True
    repo = NoteRepository()
    security = SecurityService()
    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    meeting_id = meeting.id
    with patch("src.tools._get_deps", return_value=(sync, wb, repo, security)):
        with patch("src.tools._get_db", return_value=db_session):
            result = create_task(
                name="Fix john@example.com auth bug",
                priority="high",
                meeting_id=meeting_id,
            )
    data = result if isinstance(result, dict) else json.loads(result)
    assert "task_id" in data
    assert data["notion_write_back_succeeded"] is True
    task = db_session.get(Task, data["task_id"])
    assert "john@example.com" not in task.name
    assert task.status == TaskStatus.TODO
    # Verify link
    from src.models import MeetingTasks
    link = db_session.exec(
        select(MeetingTasks).where(
            MeetingTasks.task_id == task.id,
            MeetingTasks.meeting_id == meeting_id,
        )
    ).first()
    assert link is not None
