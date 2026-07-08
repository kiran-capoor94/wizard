"""Scenario: save_note auto-synthesises mental_model via ctx.sample when agent omits it."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from wizard.models import Note, NoteType, Task, TaskCategory, TaskPriority, TaskStatus
from wizard.repositories.note import NoteRepository


@pytest.mark.asyncio
async def test_mental_model_synthesised_on_second_note(mcp_client, seed_task):
    """On 2nd note with no mental_model and ctx.sample available, one is synthesised."""
    task = await seed_task(name="synth mm task")
    await mcp_client.call_tool("session_start", {})

    r1 = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "Traced the auth middleware. Token expiry check missing.",
    })
    assert not r1.is_error, r1
    assert not r1.structured_content["mental_model_saved"]

    with patch(
        "wizard.tools.task_tools.sample_mental_model",
        new=AsyncMock(return_value="Auth middleware lacks expiry. Fix: add check in verify()."),
    ):
        r2 = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": "Confirmed: jwt.verify() never called on refresh path.",
        })
    assert not r2.is_error, r2
    assert r2.structured_content["mental_model_saved"]


@pytest.mark.asyncio
async def test_mental_model_not_synthesised_when_already_exists(mcp_client, seed_task):
    """ctx.sample is NOT called when a mental model already exists for the task."""
    task = await seed_task(name="existing mm task")
    await mcp_client.call_tool("session_start", {})

    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "First note.",
        "mental_model": "Already have a model.",
    })

    with patch(
        "wizard.tools.task_tools.sample_mental_model",
        new=AsyncMock(return_value="should not appear"),
    ) as mock_sample:
        r2 = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": "Second note — model already present.",
        })
    mock_sample.assert_not_called()
    assert not r2.is_error, r2


@pytest.mark.asyncio
async def test_mental_model_synthesis_silent_on_failure(mcp_client, seed_task):
    """If sample_mental_model raises, save_note still succeeds."""
    task = await seed_task(name="synth failure task")
    await mcp_client.call_tool("session_start", {})

    await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "INVESTIGATION", "content": "First note.",
    })

    with patch(
        "wizard.tools.task_tools.sample_mental_model",
        new=AsyncMock(side_effect=RuntimeError("transport broken")),
    ):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": "Second note — synthesis will fail.",
        })
    assert not r.is_error, r
    assert not r.structured_content["mental_model_saved"]


# ── Unit-level coverage for the helpers the scenarios above exercise indirectly ──────

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
    """sample_mental_model silently swallows exceptions and returns None."""
    from wizard.tools.task_tools import sample_mental_model

    ctx = MagicMock()
    ctx.sample = AsyncMock(side_effect=RuntimeError("transport broken"))

    result = await sample_mental_model(ctx, "some content", NoteType.INVESTIGATION)
    assert result is None


@pytest.mark.asyncio
async def test_sample_mental_model_returns_none_for_null_response():
    """sample_mental_model returns None when LLM returns the literal string 'null'."""
    from wizard.tools.task_tools import sample_mental_model

    mock_result = MagicMock()
    mock_result.text = "null"

    ctx = MagicMock()
    ctx.sample = AsyncMock(return_value=mock_result)

    result = await sample_mental_model(ctx, "too short", NoteType.OBSERVATION)
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
