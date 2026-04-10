from unittest.mock import patch

from tests.helpers import mock_session


def test_open_tasks_resource(db_session):
    from src.models import Task, TaskStatus
    from src.resources import open_tasks
    from src.schemas import OpenTasksResource

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()

    with patch("src.resources.get_session", mock_session(db_session)):
        result = open_tasks()

    assert isinstance(result, OpenTasksResource)
    assert len(result.tasks) == 1
    assert result.tasks[0].name == "Fix auth"


def test_open_tasks_resource_empty(db_session):
    from src.resources import open_tasks
    from src.schemas import OpenTasksResource

    with patch("src.resources.get_session", mock_session(db_session)):
        result = open_tasks()

    assert isinstance(result, OpenTasksResource)
    assert len(result.tasks) == 0


def test_blocked_tasks_resource(db_session):
    from src.models import Task, TaskStatus
    from src.resources import blocked_tasks
    from src.schemas import BlockedTasksResource

    task = Task(name="Blocked task", status=TaskStatus.BLOCKED)
    db_session.add(task)
    db_session.commit()

    with patch("src.resources.get_session", mock_session(db_session)):
        result = blocked_tasks()

    assert isinstance(result, BlockedTasksResource)
    assert len(result.tasks) == 1
    assert result.tasks[0].name == "Blocked task"


def test_current_session_resource_active(db_session):
    from src.models import WizardSession, Task, TaskStatus
    from src.resources import current_session
    from src.schemas import SessionResource

    session = WizardSession()
    task = Task(name="Open task", status=TaskStatus.TODO)
    db_session.add(session)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(session)

    with patch("src.resources.get_session", mock_session(db_session)):
        result = current_session()

    assert isinstance(result, SessionResource)
    assert result.session_id == session.id
    assert result.open_task_count == 1
    assert result.blocked_task_count == 0


def test_current_session_resource_none(db_session):
    from src.resources import current_session
    from src.schemas import SessionResource

    with patch("src.resources.get_session", mock_session(db_session)):
        result = current_session()

    assert isinstance(result, SessionResource)
    assert result.session_id is None


def test_task_context_resource(db_session):
    from src.models import Task, TaskStatus, Note, NoteType
    from src.resources import task_context
    from src.schemas import TaskContextResource

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS, source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(note_type=NoteType.INVESTIGATION, content="Found root cause", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    with patch("src.resources.get_session", mock_session(db_session)):
        result = task_context(task_id=task.id)

    assert isinstance(result, TaskContextResource)
    assert result.task.name == "Fix auth"
    assert len(result.notes) == 1
    assert result.notes[0].content == "Found root cause"


def test_config_resource(db_session):
    from src.resources import wizard_config
    from src.schemas import ConfigResource

    result = wizard_config()

    assert isinstance(result, ConfigResource)
    assert isinstance(result.jira_enabled, bool)
    assert isinstance(result.notion_enabled, bool)
    assert isinstance(result.scrubbing_enabled, bool)
    assert isinstance(result.database_path, str)
