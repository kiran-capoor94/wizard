import json
from unittest.mock import patch

from fastmcp.resources import ResourceResult
from tests.helpers import mock_session


def _parse_resource(result):
    """Extract parsed JSON from a ResourceResult."""
    assert isinstance(result, ResourceResult)
    return json.loads(result.contents[0].content)


def test_open_tasks_resource(db_session):
    from src.models import Task, TaskStatus
    from src.resources import open_tasks

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()

    with patch("src.resources.get_session", mock_session(db_session)):
        result = open_tasks()

    data = _parse_resource(result)
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["name"] == "Fix auth"


def test_open_tasks_resource_empty(db_session):
    from src.resources import open_tasks

    with patch("src.resources.get_session", mock_session(db_session)):
        result = open_tasks()

    data = _parse_resource(result)
    assert len(data["tasks"]) == 0


def test_blocked_tasks_resource(db_session):
    from src.models import Task, TaskStatus
    from src.resources import blocked_tasks

    task = Task(name="Blocked task", status=TaskStatus.BLOCKED)
    db_session.add(task)
    db_session.commit()

    with patch("src.resources.get_session", mock_session(db_session)):
        result = blocked_tasks()

    data = _parse_resource(result)
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["name"] == "Blocked task"


def test_current_session_resource_active(db_session):
    from src.models import WizardSession, Task, TaskStatus
    from src.resources import current_session

    session = WizardSession()
    task = Task(name="Open task", status=TaskStatus.TODO)
    db_session.add(session)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(session)

    with patch("src.resources.get_session", mock_session(db_session)):
        result = current_session()

    data = _parse_resource(result)
    assert data["session_id"] == session.id
    assert data["open_task_count"] == 1
    assert data["blocked_task_count"] == 0


def test_current_session_resource_none(db_session):
    from src.resources import current_session

    with patch("src.resources.get_session", mock_session(db_session)):
        result = current_session()

    data = _parse_resource(result)
    assert data["session_id"] is None


def test_task_context_resource(db_session):
    from src.models import Task, TaskStatus, Note, NoteType
    from src.resources import task_context

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

    data = _parse_resource(result)
    assert data["task"]["name"] == "Fix auth"
    assert len(data["notes"]) == 1
    assert data["notes"][0]["content"] == "Found root cause"


def test_config_resource(db_session):
    from src.resources import wizard_config

    result = wizard_config()

    data = _parse_resource(result)
    assert isinstance(data["jira_enabled"], bool)
    assert isinstance(data["notion_enabled"], bool)
    assert isinstance(data["scrubbing_enabled"], bool)
    assert isinstance(data["database_path"], str)
