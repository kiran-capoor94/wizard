import datetime


# ---------------------------------------------------------------------------
# NoteRepository
# ---------------------------------------------------------------------------

def test_save_note(db_session):
    from wizard.models import Note, NoteType
    from wizard.repositories import NoteRepository
    repo = NoteRepository()
    note = Note(note_type=NoteType.INVESTIGATION, content="looking into AUTH-123")
    saved = repo.save(db_session, note)
    assert saved.id is not None


def test_get_for_task_by_task_id(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository
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
    from wizard.models import Note, NoteType
    from wizard.repositories import NoteRepository
    repo = NoteRepository()
    note = Note(note_type=NoteType.DECISION, content="from notion", source_id="AUTH-123")
    repo.save(db_session, note)

    results = repo.get_for_task(db_session, task_id=None, source_id="AUTH-123")
    assert len(results) == 1
    assert results[0].source_id == "AUTH-123"


def test_get_for_task_or_semantics(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository
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


def test_get_for_task_returns_latest_first(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository
    repo = NoteRepository()
    task = Task(name="fix auth", source_id="AUTH-456")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    n1 = Note(
        note_type=NoteType.INVESTIGATION, content="first", task_id=task.id,
        created_at=datetime.datetime(2026, 1, 1, 12, 0, 0),
    )
    repo.save(db_session, n1)
    n2 = Note(
        note_type=NoteType.DECISION, content="second", task_id=task.id,
        created_at=datetime.datetime(2026, 1, 1, 12, 1, 0),
    )
    repo.save(db_session, n2)

    results = repo.get_for_task(db_session, task_id=task.id, source_id=None)
    assert len(results) == 2
    assert results[0].content == "second"


def test_get_for_task_returns_empty_when_no_match(db_session):
    from wizard.repositories import NoteRepository
    repo = NoteRepository()
    results = repo.get_for_task(db_session, task_id=999, source_id=None)
    assert results == []


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
    from wizard.models import Task, TaskStatus, TaskPriority
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


def test_build_task_context_includes_latest_note(db_session):
    from wizard.models import Task, TaskStatus, Note, NoteType
    from wizard.repositories import TaskRepository
    repo = TaskRepository()
    task = Task(name="fix auth", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    note = Note(note_type=NoteType.INVESTIGATION, content="found the issue", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    ctx = repo.build_task_context(db_session, task)
    assert ctx.last_note_type == NoteType.INVESTIGATION
    assert ctx.last_note_preview == "found the issue"


# ---------------------------------------------------------------------------
# MeetingRepository
# ---------------------------------------------------------------------------

def test_meeting_get_by_id(db_session):
    from wizard.models import Meeting
    from wizard.repositories import MeetingRepository
    repo = MeetingRepository()
    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    assert meeting.id is not None

    found = repo.get_by_id(db_session, meeting.id)
    assert found.title == "standup"


def test_meeting_get_by_id_raises_when_missing(db_session):
    import pytest
    from wizard.repositories import MeetingRepository
    repo = MeetingRepository()
    with pytest.raises(ValueError, match="Meeting 999 not found"):
        repo.get_by_id(db_session, 999)


def test_unsummarised_contexts(db_session):
    from wizard.models import Meeting
    from wizard.repositories import MeetingRepository
    repo = MeetingRepository()
    unsummarised = Meeting(title="standup", content="notes")
    summarised = Meeting(title="retro", content="notes", summary="done")
    db_session.add_all([unsummarised, summarised])
    db_session.commit()

    contexts = repo.get_unsummarised_contexts(db_session)
    assert len(contexts) == 1
    assert contexts[0].title == "standup"
    assert contexts[0].has_summary is False
