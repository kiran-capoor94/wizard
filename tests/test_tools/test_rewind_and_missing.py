from unittest.mock import patch

from tests.helpers import MockContext, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# rewind_task
# ---------------------------------------------------------------------------


async def test_rewind_task_empty_timeline(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import TaskStateRepository as _TaskStateRepo
    from wizard.tools import rewind_task

    def task_state_repo():
        return _TaskStateRepo()

    task = Task(name="empty task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository
        result = await rewind_task(ctx, task_id=task.id, n_repo=NoteRepository())

    assert result.timeline == []
    assert result.summary.total_notes == 0
    assert result.summary.duration_days == 0


async def test_what_am_i_missing_stale_2_days_fires_lost_context_not_stale(db_session):
    """stale_days=2 with notes → lost_context fires; stale must NOT fire (threshold is >= 3)."""
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
    from wizard.tools import what_am_i_missing

    task = Task(name="T", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="some work")
    db_session.add(note)
    db_session.flush()
    db_session.refresh(note)

    last_note = datetime.datetime.now() - datetime.timedelta(days=2)
    state = TaskState(
        task_id=task.id,
        note_count=1,
        decision_count=0,
        last_note_at=last_note,
        last_touched_at=last_note,
        stale_days=2,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        result = await what_am_i_missing(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    signal_types = [s.type for s in result.signals]
    assert "lost_context" in signal_types
    assert "stale" not in signal_types


async def test_what_am_i_missing_stale_3_days_fires_stale_not_lost_context(db_session):
    """stale_days=3 with notes → stale fires; lost_context must NOT fire (no double-signal)."""
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
    from wizard.tools import what_am_i_missing

    task = Task(name="T", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="some work")
    db_session.add(note)
    db_session.flush()
    db_session.refresh(note)

    last_note = datetime.datetime.now() - datetime.timedelta(days=3)
    state = TaskState(
        task_id=task.id,
        note_count=1,
        decision_count=0,
        last_note_at=last_note,
        last_touched_at=last_note,
        stale_days=3,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        result = await what_am_i_missing(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    signal_types = [s.type for s in result.signals]
    assert "stale" in signal_types
    assert "lost_context" not in signal_types
