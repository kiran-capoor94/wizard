import json
import time
from typing import Generator

import pytest
from sqlmodel import Session, SQLModel


@pytest.fixture(autouse=True)
def db_session(monkeypatch, tmp_path) -> Generator[Session, None, None]:
    import sys

    # Point settings at an in-memory DB so tests never touch wizard.db
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))
    # Force re-import so the engine is built with the in-memory URL
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    monkeypatch.delitem(sys.modules, "src.database", raising=False)
    monkeypatch.delitem(sys.modules, "src.models", raising=False)
    SQLModel.metadata.clear()
    SQLModel._sa_registry.dispose(cascade=True)

    from src.database import engine
    import src.models  # noqa: F401 — registers all table models with SQLModel.metadata

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


def test_created_at_is_not_frozen_at_module_load(db_session):
    from src.models import Task

    t1 = Task(name="first")
    db_session.add(t1)
    db_session.commit()
    db_session.refresh(t1)

    time.sleep(0.05)

    t2 = Task(name="second")
    db_session.add(t2)
    db_session.commit()
    db_session.refresh(t2)

    assert t1.created_at != t2.created_at


def test_task_has_updated_at_field(db_session):
    from src.models import Task

    task = Task(name="foo")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.updated_at is not None


def test_updated_at_changes_on_update(db_session):
    from src.models import Task

    task = Task(name="foo")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    original_updated_at = task.updated_at

    time.sleep(0.05)

    task.name = "bar"
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.updated_at > original_updated_at


def test_task_can_be_created_without_due_date(db_session):
    from src.models import Task

    task = Task(name="no deadline")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.due_date is None


def test_meeting_tasks_relationship(db_session):
    from src.models import Meeting, MeetingTasks, Task

    meeting = Meeting(content="standup notes")
    task = Task(name="action item")
    db_session.add(meeting)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(meeting)
    db_session.refresh(task)

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(meeting)

    assert len(meeting.tasks) == 1
    assert meeting.tasks[0].id == task.id


def test_task_meetings_relationship(db_session):
    from src.models import Meeting, MeetingTasks, Task

    meeting = Meeting(content="planning notes")
    task = Task(name="action item")
    db_session.add(meeting)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(meeting)
    db_session.refresh(task)

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(task)

    assert len(task.meetings) == 1
    assert task.meetings[0].id == meeting.id


def test_invalid_enum_value_rejected():
    from pydantic import ValidationError

    from src.models import Task

    with pytest.raises(ValidationError):
        Task(name="test", priority="invalid_value")
