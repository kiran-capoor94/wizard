import json
from unittest.mock import patch

from fastmcp.resources import ResourceResult
from tests.helpers import mock_session


def _parse_resource(result):
    """Extract parsed JSON from a ResourceResult."""
    assert isinstance(result, ResourceResult)
    return json.loads(result.contents[0].content)


def test_open_tasks_resource(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import TaskRepository
    from wizard.resources import open_tasks

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()

    with patch("wizard.resources.get_session", mock_session(db_session)):
        result = open_tasks(t_repo=TaskRepository())

    data = _parse_resource(result)
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["name"] == "Fix auth"


def test_open_tasks_resource_empty(db_session):
    from wizard.repositories import TaskRepository
    from wizard.resources import open_tasks

    with patch("wizard.resources.get_session", mock_session(db_session)):
        result = open_tasks(t_repo=TaskRepository())

    data = _parse_resource(result)
    assert len(data["tasks"]) == 0


def test_blocked_tasks_resource(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import TaskRepository
    from wizard.resources import blocked_tasks

    task = Task(name="Blocked task", status=TaskStatus.BLOCKED)
    db_session.add(task)
    db_session.commit()

    with patch("wizard.resources.get_session", mock_session(db_session)):
        result = blocked_tasks(t_repo=TaskRepository())

    data = _parse_resource(result)
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["name"] == "Blocked task"


def test_current_session_resource_active(db_session):
    from wizard.models import WizardSession, Task, TaskStatus
    from wizard.repositories import TaskRepository
    from wizard.resources import current_session

    session = WizardSession()
    task = Task(name="Open task", status=TaskStatus.TODO)
    db_session.add(session)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(session)

    with patch("wizard.resources.get_session", mock_session(db_session)):
        result = current_session(t_repo=TaskRepository())

    data = _parse_resource(result)
    assert data["session_id"] == session.id
    assert data["open_task_count"] == 1
    assert data["blocked_task_count"] == 0


def test_current_session_resource_none(db_session):
    from wizard.repositories import TaskRepository
    from wizard.resources import current_session

    with patch("wizard.resources.get_session", mock_session(db_session)):
        result = current_session(t_repo=TaskRepository())

    data = _parse_resource(result)
    assert data["session_id"] is None


def test_task_context_resource(db_session):
    from wizard.models import Task, TaskStatus, Note, NoteType
    from wizard.repositories import TaskRepository, NoteRepository
    from wizard.resources import task_context

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS, source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(note_type=NoteType.INVESTIGATION, content="Found root cause", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    with patch("wizard.resources.get_session", mock_session(db_session)):
        result = task_context(task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    data = _parse_resource(result)
    assert data["task"]["name"] == "Fix auth"
    assert len(data["notes"]) == 1
    assert data["notes"][0]["content"] == "Found root cause"


def test_config_resource(db_session):
    from wizard.resources import wizard_config

    result = wizard_config()

    data = _parse_resource(result)
    assert isinstance(data["jira_enabled"], bool)
    assert isinstance(data["notion_enabled"], bool)
    assert isinstance(data["scrubbing_enabled"], bool)
    assert isinstance(data["database_path"], str)
