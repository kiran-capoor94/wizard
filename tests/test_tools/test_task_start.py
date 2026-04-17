from unittest.mock import patch

from tests.helpers import MockContext, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# task_start
# ---------------------------------------------------------------------------


async def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(
        note_type=NoteType.INVESTIGATION, content="prior investigation", task_id=task.id
    )
    db_session.add(note)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.compounding is True
    assert len(result.prior_notes) == 1


async def test_task_start_returns_compounding_false_when_no_notes(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    task = Task(name="new task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.compounding is False


async def test_task_start_raises_when_task_not_found(db_session):
    import pytest
    from fastmcp.exceptions import ToolError

    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        with pytest.raises(ToolError, match="Task 999 not found"):
            await task_start(ctx, task_id=999, t_repo=TaskRepository(), n_repo=NoteRepository())


async def test_task_start_latest_mental_model_returns_newest_note_model(db_session):
    import datetime

    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    task = Task(name="state machine refactor")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    # older note — has a mental_model but should NOT be returned
    older_note = Note(
        note_type=NoteType.INVESTIGATION,
        content="earlier investigation",
        task_id=task.id,
        mental_model="Observer pattern",
        created_at=datetime.datetime(2024, 1, 1, 10, 0, 0),
    )
    # newer note — has a mental_model and SHOULD be returned
    newer_note = Note(
        note_type=NoteType.DECISION,
        content="decision made",
        task_id=task.id,
        mental_model="State machine",
        created_at=datetime.datetime(2024, 1, 2, 10, 0, 0),
    )
    db_session.add(older_note)
    db_session.add(newer_note)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.latest_mental_model == "State machine"


async def test_task_start_latest_mental_model_none_when_no_notes_have_model(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    task = Task(name="simple fix")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(
        note_type=NoteType.INVESTIGATION,
        content="investigation without model",
        task_id=task.id,
        mental_model=None,
    )
    db_session.add(note)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.latest_mental_model is None


async def test_task_start_returns_prior_notes_oldest_first(db_session):
    """prior_notes must be ordered oldest-first (matching rewind_task convention)."""
    import datetime

    from wizard.models import (
        Note,
        NoteType,
        Task,
        TaskCategory,
        TaskPriority,
        TaskState,
        TaskStatus,
    )
    from wizard.tools import task_start

    task = Task(
        name="Fix auth",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    state = TaskState(
        task_id=task.id,
        note_count=2,
        decision_count=0,
        last_touched_at=datetime.datetime.now(),
        stale_days=0,
    )
    db_session.add(state)

    older = Note(
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="older note",
        created_at=datetime.datetime(2026, 1, 1, 10, 0, 0),
    )
    newer = Note(
        task_id=task.id,
        note_type=NoteType.DECISION,
        content="newer note",
        created_at=datetime.datetime(2026, 1, 3, 10, 0, 0),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert len(result.prior_notes) == 2
    assert result.prior_notes[0].content == "older note"
    assert result.prior_notes[1].content == "newer note"
