import json
import pytest
from unittest.mock import MagicMock


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
