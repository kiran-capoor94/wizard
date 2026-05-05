"""Scenario: save_note auto-synthesises mental model when agent omits it."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine

from wizard.models import Note, NoteType, Task, TaskCategory, TaskPriority, TaskStatus
from wizard.repositories.note import NoteRepository


@pytest.fixture
def mem_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_task(db) -> Task:
    task = Task(
        name="test task", priority=TaskPriority.MEDIUM,
        status=TaskStatus.TODO, category=TaskCategory.ISSUE,
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


@pytest.mark.asyncio
async def test_sample_mental_model_returns_none_on_exception():
    """_sample_mental_model silently swallows exceptions and returns None."""
    from wizard.tools.task_tools import _sample_mental_model

    ctx = MagicMock()
    ctx.sample = AsyncMock(side_effect=RuntimeError("transport broken"))

    result = await _sample_mental_model(ctx, "some content", NoteType.INVESTIGATION)
    assert result is None


@pytest.mark.asyncio
async def test_sample_mental_model_returns_none_for_null_response():
    """_sample_mental_model returns None when LLM returns the literal string 'null'."""
    from wizard.tools.task_tools import _sample_mental_model

    mock_result = MagicMock()
    mock_result.text = "null"

    ctx = MagicMock()
    ctx.sample = AsyncMock(return_value=mock_result)

    result = await _sample_mental_model(ctx, "too short", NoteType.OBSERVATION)
    assert result is None


def test_count_for_task_and_has_mental_model_integration(mem_db):
    """Repository methods used by Phase 4 behave correctly together."""
    task = _make_task(mem_db)
    repo = NoteRepository()

    # No notes: count=0, has_mental_model=False
    assert repo.count_for_task(mem_db, task.id) == 0
    assert not repo.has_mental_model(mem_db, task.id)

    # Add first note (no mental model)
    note1 = Note(note_type=NoteType.INVESTIGATION, content="first", task_id=task.id)
    mem_db.add(note1)
    mem_db.flush()
    assert repo.count_for_task(mem_db, task.id) == 1
    assert not repo.has_mental_model(mem_db, task.id)

    # Add second note — count >= 2, still no mental model: should_synthesise = True
    note2 = Note(note_type=NoteType.DECISION, content="decided", task_id=task.id)
    mem_db.add(note2)
    mem_db.flush()
    assert repo.count_for_task(mem_db, task.id) == 2
    should_synthesise = repo.count_for_task(mem_db, task.id) >= 2 and not repo.has_mental_model(mem_db, task.id)
    assert should_synthesise

    # After set_mental_model: has_mental_model=True, should_synthesise=False
    mem_db.refresh(note2)
    repo.set_mental_model(mem_db, note2.id, "Current understanding: X is broken.")
    assert repo.has_mental_model(mem_db, task.id)
    should_synthesise = repo.count_for_task(mem_db, task.id) >= 2 and not repo.has_mental_model(mem_db, task.id)
    assert not should_synthesise
