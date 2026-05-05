"""Scenario: OBSERVATION note type exists and behaves correctly across the stack."""
import pytest
from sqlmodel import Session, SQLModel, create_engine

from wizard.models import Note, NoteType, Task, TaskCategory, TaskPriority, TaskStatus
from wizard.repositories.note import NoteRepository


def test_observation_note_type_exists():
    """NoteType.OBSERVATION is a valid enum value."""
    assert NoteType.OBSERVATION == "observation"
    assert NoteType("observation") is NoteType.OBSERVATION


@pytest.fixture
def note_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_task(db):
    task = Task(
        name="test task", priority=TaskPriority.MEDIUM,
        status=TaskStatus.TODO, category=TaskCategory.ISSUE,
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def test_count_for_task_empty(note_db):
    """count_for_task returns 0 when task has no notes."""
    task = _make_task(note_db)
    assert NoteRepository().count_for_task(note_db, task.id) == 0


def test_count_for_task_counts_all_types(note_db):
    """count_for_task counts all note types including OBSERVATION."""
    task = _make_task(note_db)
    repo = NoteRepository()
    for nt in [NoteType.INVESTIGATION, NoteType.OBSERVATION, NoteType.DECISION]:
        note_db.add(Note(note_type=nt, content="x", task_id=task.id))
    note_db.flush()
    assert repo.count_for_task(note_db, task.id) == 3


def test_set_mental_model_patches_note(note_db):
    """set_mental_model updates mental_model on an existing note."""
    task = _make_task(note_db)
    note = Note(note_type=NoteType.OBSERVATION, content="raw msg", task_id=task.id)
    note_db.add(note)
    note_db.flush()
    note_db.refresh(note)
    NoteRepository().set_mental_model(note_db, note.id, "Current understanding: X.")
    note_db.refresh(note)
    assert note.mental_model == "Current understanding: X."
