import pytest
import time


def test_save_note(db_session):
    from src.models import Note, NoteType
    from src.repositories import NoteRepository
    repo = NoteRepository()
    note = Note(note_type=NoteType.INVESTIGATION, content="looking into AUTH-123")
    saved = repo.save(db_session, note)
    assert saved.id is not None


def test_get_for_task_by_task_id(db_session):
    from src.models import Note, NoteType, Task
    from src.repositories import NoteRepository
    repo = NoteRepository()
    task = Task(name="fix auth", source_id="AUTH-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    note = Note(note_type=NoteType.INVESTIGATION, content="auth notes", task_id=task.id)
    repo.save(db_session, note)

    results = repo.get_for_task(db_session, task_id=task.id, source_id=None)
    assert len(results) == 1
    assert results[0].content == "auth notes"


def test_get_for_task_by_source_id(db_session):
    from src.models import Note, NoteType
    from src.repositories import NoteRepository
    repo = NoteRepository()
    note = Note(note_type=NoteType.DECISION, content="from notion", source_id="AUTH-123")
    repo.save(db_session, note)

    results = repo.get_for_task(db_session, task_id=None, source_id="AUTH-123")
    assert len(results) == 1
    assert results[0].source_id == "AUTH-123"


def test_get_for_task_or_semantics(db_session):
    from src.models import Note, NoteType, Task
    from src.repositories import NoteRepository
    repo = NoteRepository()
    task = Task(name="fix auth", source_id="AUTH-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    note1 = Note(note_type=NoteType.INVESTIGATION, content="by task_id", task_id=task.id)
    note2 = Note(note_type=NoteType.DECISION, content="by source_id", source_id="AUTH-123")
    repo.save(db_session, note1)
    repo.save(db_session, note2)

    results = repo.get_for_task(db_session, task_id=task.id, source_id="AUTH-123")
    assert len(results) == 2


def test_get_latest_for_task(db_session):
    from src.models import Note, NoteType, Task
    from src.repositories import NoteRepository
    repo = NoteRepository()
    task = Task(name="fix auth", source_id="AUTH-456")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    n1 = Note(note_type=NoteType.INVESTIGATION, content="first", task_id=task.id)
    repo.save(db_session, n1)
    time.sleep(0.05)
    n2 = Note(note_type=NoteType.DECISION, content="second", task_id=task.id)
    repo.save(db_session, n2)

    latest = repo.get_latest_for_task(db_session, task_id=task.id, source_id=None)
    assert latest is not None
    assert latest.content == "second"


def test_get_latest_for_task_returns_none_when_empty(db_session):
    from src.repositories import NoteRepository
    repo = NoteRepository()
    result = repo.get_latest_for_task(db_session, task_id=999, source_id=None)
    assert result is None
