# ---------------------------------------------------------------------------
# TaskRepository
# ---------------------------------------------------------------------------

def test_task_get_by_id(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import TaskRepository
    repo = TaskRepository()
    task = Task(name="fix auth", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    found = repo.get_by_id(db_session, task.id)
    assert found.name == "fix auth"


def test_task_get_by_id_raises_when_missing(db_session):
    import pytest

    from wizard.repositories import TaskRepository
    repo = TaskRepository()
    with pytest.raises(ValueError, match="Task 999 not found"):
        repo.get_by_id(db_session, 999)


def test_open_task_contexts_sorted_by_priority(db_session):
    from wizard.models import Task, TaskPriority, TaskStatus
    from wizard.repositories import TaskRepository
    repo = TaskRepository()
    low = Task(name="low", status=TaskStatus.TODO, priority=TaskPriority.LOW)
    high = Task(name="high", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.HIGH)
    med = Task(name="med", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM)
    db_session.add_all([low, high, med])
    db_session.commit()

    contexts = repo.get_open_task_contexts(db_session)
    names = [c.name for c in contexts]
    assert names == ["high", "med", "low"]


def test_blocked_task_contexts(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import TaskRepository
    repo = TaskRepository()
    blocked = Task(name="blocked", status=TaskStatus.BLOCKED)
    done = Task(name="done", status=TaskStatus.DONE)
    db_session.add_all([blocked, done])
    db_session.commit()

    contexts = repo.get_blocked_task_contexts(db_session)
    assert len(contexts) == 1
    assert contexts[0].name == "blocked"


def test_get_task_context_includes_latest_note(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.repositories import TaskRepository
    repo = TaskRepository()
    task = Task(name="fix auth", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    note = Note(note_type=NoteType.INVESTIGATION, content="found the issue", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    ctx = repo.get_task_context(db_session, task)
    assert ctx.last_note_type == NoteType.INVESTIGATION
    assert ctx.last_note_preview == "found the issue"


# ---------------------------------------------------------------------------
# TaskContext construction via TaskState
# ---------------------------------------------------------------------------

def test_get_task_context_includes_task_state_fields(db_session):
    from wizard.models import Task, TaskCategory, TaskPriority, TaskState, TaskStatus
    from wizard.repositories import TaskRepository
    repo = TaskRepository()

    task = Task(
        name="T",
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
        category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()
    assert task.id is not None

    import datetime as _dt
    ts = TaskState(
        task_id=task.id,
        stale_days=4,
        note_count=2,
        decision_count=0,
        last_touched_at=_dt.datetime.now(),
    )
    db_session.add(ts)
    db_session.flush()

    ctx = repo.get_task_context(db_session, task)
    assert ctx.stale_days == 4
    assert ctx.note_count == 2
