import datetime

from wizard.models import Note, NoteType, Task
from wizard.repositories.task_state import TaskStateRepository


def _make_task(db) -> Task:
    task = Task(
        name="Test Task", status="todo", priority="medium", category="issue",
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def _make_note(db, task_id: int, note_type=NoteType.INVESTIGATION) -> Note:
    note = Note(
        note_type=note_type, content="some content", task_id=task_id,
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    db.add(note)
    db.flush()
    db.refresh(note)
    return note


def test_on_note_saved_increments_note_count(db_session):
    repo = TaskStateRepository()
    task = _make_task(db_session)
    state = repo.create_for_task(db_session, task)
    assert state.note_count == 0

    _make_note(db_session, task.id)
    state = repo.on_note_saved(db_session, task.id, NoteType.INVESTIGATION)
    assert state.note_count == 1
    assert state.decision_count == 0

    _make_note(db_session, task.id, NoteType.DECISION)
    state = repo.on_note_saved(db_session, task.id, NoteType.DECISION)
    assert state.note_count == 2
    assert state.decision_count == 1


def test_on_note_saved_does_not_select_all_notes(db_session, monkeypatch):
    repo = TaskStateRepository()
    task = _make_task(db_session)
    repo.create_for_task(db_session, task)
    _make_note(db_session, task.id)

    exec_calls = []
    original_exec = db_session.exec
    def tracking_exec(stmt, *args, **kwargs):
        exec_calls.append(str(stmt))
        return original_exec(stmt, *args, **kwargs)
    monkeypatch.setattr(db_session, "exec", tracking_exec)

    repo.on_note_saved(db_session, task.id, NoteType.INVESTIGATION)
    # Should not have any SELECT on Note without a mental_model filter
    full_note_selects = [s for s in exec_calls if "note" in s.lower() and "mental_model" not in s.lower()]
    assert len(full_note_selects) == 0, f"Unexpected full note selects: {full_note_selects}"
