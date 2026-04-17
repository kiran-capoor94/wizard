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
    note = Note(note_type=NoteType.DECISION, content="from notion", source_id="AUTH-123", source_type="JIRA")
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
    note2 = Note(note_type=NoteType.DECISION, content="by source_id", source_id="AUTH-123", source_type="JIRA")
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


def test_get_for_task_source_type_guard_excludes_non_jira(db_session):
    """source_id match requires source_type == 'JIRA' — prevents UUID collisions."""
    from wizard.models import Note, NoteType
    from wizard.repositories import NoteRepository
    repo = NoteRepository()

    # Note with matching source_id but wrong source_type — must be excluded
    note = Note(
        note_type=NoteType.DECISION,
        content="notion-only note",
        source_id="AUTH-999",
        source_type="NOTION",
    )
    repo.save(db_session, note)

    results = repo.get_for_task(db_session, task_id=None, source_id="AUTH-999")
    assert len(results) == 0


def test_get_for_task_source_type_guard_includes_jira(db_session):
    """source_id match with source_type == 'JIRA' is included."""
    from wizard.models import Note, NoteType
    from wizard.repositories import NoteRepository
    repo = NoteRepository()

    note = Note(
        note_type=NoteType.INVESTIGATION,
        content="jira note",
        source_id="PD-42",
        source_type="JIRA",
    )
    repo.save(db_session, note)

    results = repo.get_for_task(db_session, task_id=None, source_id="PD-42")
    assert len(results) == 1
    assert results[0].source_type == "JIRA"


async def test_save_note_propagates_source_type_from_task(db_session):
    """save_note copies source_type from the task onto the note."""
    from unittest.mock import MagicMock, patch

    from tests.helpers import MockContext, mock_session
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
    from wizard.security import SecurityService
    from wizard.tools import save_note

    task = Task(name="auth fix", source_id="PD-10", source_type="JIRA")
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    assert task.id is not None

    content = "found the bug"
    sec_mock = MagicMock(spec=SecurityService)
    sec_mock.scrub.return_value.clean = content

    ctx = MockContext()
    patches = {
        "get_session": mock_session(db_session),
    }
    with patch.multiple("wizard.tools._helpers", **patches):  # type: ignore[arg-type]
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content=content,
            t_repo=TaskRepository(),
            sec=sec_mock,
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.source_id == "PD-10"
    assert note.source_type == "JIRA"


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


def test_build_task_context_includes_latest_note(db_session):
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
    assert contexts[0].already_summarised is False


# ---------------------------------------------------------------------------
# TaskStateRepository
# ---------------------------------------------------------------------------

class TestTaskStateRepository:
    def test_create_for_task_initialises_zero_state(self, db_session):
        from wizard.models import Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        repo = TaskStateRepository()
        state = repo.create_for_task(db_session, task)

        assert state.task_id == task.id
        assert state.note_count == 0
        assert state.decision_count == 0
        assert state.last_note_at is None
        assert state.last_status_change_at is None
        assert state.last_touched_at == task.created_at
        assert state.stale_days >= 0

    def test_create_for_task_persists_row(self, db_session):
        from wizard.models import Task, TaskState
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        loaded = db_session.get(TaskState, task.id)
        assert loaded is not None
        assert loaded.task_id == task.id

    def test_on_note_saved_increments_note_count(self, db_session):
        from wizard.models import Note, NoteType, Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        note = Note(note_type=NoteType.INVESTIGATION, content="i", task_id=task.id)
        db_session.add(note)
        db_session.flush()

        state = repo.on_note_saved(db_session, task.id)
        assert state.note_count == 1
        assert state.decision_count == 0
        assert state.last_note_at == note.created_at
        assert state.last_touched_at == note.created_at

    def test_on_note_saved_counts_decisions(self, db_session):
        from wizard.models import Note, NoteType, Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        for nt, content in [
            (NoteType.INVESTIGATION, "i1"),
            (NoteType.DECISION, "d1"),
            (NoteType.DECISION, "d2"),
            (NoteType.DOCS, "doc1"),
        ]:
            db_session.add(Note(note_type=nt, content=content, task_id=task.id))
            db_session.flush()
            repo.on_note_saved(db_session, task.id)

        from wizard.models import TaskState
        state = db_session.get(TaskState, task.id)
        assert state is not None
        assert state.note_count == 4
        assert state.decision_count == 2

    def test_on_note_saved_does_not_touch_last_status_change_at(self, db_session):
        import datetime as _dt

        from wizard.models import Note, NoteType, Task, TaskState
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        sentinel = _dt.datetime(2020, 1, 1, 12, 0, 0)
        state = db_session.get(TaskState, task.id)
        assert state is not None
        state.last_status_change_at = sentinel
        db_session.add(state)
        db_session.flush()

        db_session.add(Note(note_type=NoteType.INVESTIGATION, content="x", task_id=task.id))
        db_session.flush()
        result = repo.on_note_saved(db_session, task.id)

        assert result.last_status_change_at == sentinel

    def test_on_note_saved_dual_lookup_finds_jira_anchored_notes(self, db_session):
        from wizard.models import Note, NoteType, Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t", source_id="AUTH-123", source_type="JIRA")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        # Note attached only by source_id (not task_id) — simulates an
        # earlier note saved before the task row existed locally.
        db_session.add(Note(
            note_type=NoteType.INVESTIGATION,
            content="historical",
            source_id="AUTH-123",
            source_type="JIRA",
        ))
        db_session.flush()

        state = repo.on_note_saved(db_session, task.id)
        assert state.note_count == 1

    def test_on_status_changed_sets_timestamp_and_preserves_other_fields(self, db_session):
        import datetime as _dt

        from wizard.models import Note, NoteType, Task, TaskState
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        db_session.add(Note(note_type=NoteType.INVESTIGATION, content="i", task_id=task.id))
        db_session.add(Note(note_type=NoteType.DECISION, content="d", task_id=task.id))
        db_session.flush()
        repo.on_note_saved(db_session, task.id)

        before = db_session.get(TaskState, task.id)
        assert before is not None
        old_note_count = before.note_count
        old_decision_count = before.decision_count
        old_last_note_at = before.last_note_at
        old_last_touched_at = before.last_touched_at
        old_stale_days = before.stale_days

        result = repo.on_status_changed(db_session, task.id)

        assert result.last_status_change_at is not None
        assert (_dt.datetime.now() - result.last_status_change_at).total_seconds() < 5
        assert result.note_count == old_note_count
        assert result.decision_count == old_decision_count
        assert result.last_note_at == old_last_note_at
        assert result.last_touched_at == old_last_touched_at
        assert result.stale_days == old_stale_days

    def test_on_status_changed_creates_state_if_missing(self, db_session):
        from wizard.models import Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        repo = TaskStateRepository()
        result = repo.on_status_changed(db_session, task.id)
        assert result.task_id == task.id
        assert result.last_status_change_at is not None


# ---------------------------------------------------------------------------
# TaskContext construction via TaskState
# ---------------------------------------------------------------------------

def test_build_task_context_includes_task_state_fields(db_session):
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

    ctx = repo.build_task_context(db_session, task)
    assert ctx.stale_days == 4
    assert ctx.note_count == 2


# ---------------------------------------------------------------------------
# find_latest_session_with_notes
# ---------------------------------------------------------------------------


def test_find_latest_session_with_notes_returns_none_when_no_sessions(db_session):
    from wizard.repositories import find_latest_session_with_notes
    result = find_latest_session_with_notes(db_session)
    assert result is None


def test_find_latest_session_with_notes_returns_none_when_sessions_have_no_notes(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import find_latest_session_with_notes

    s = WizardSession()
    db_session.add(s)
    db_session.flush()
    result = find_latest_session_with_notes(db_session)
    assert result is None


def test_find_latest_session_with_notes_returns_most_recent_session_with_notes(db_session):
    import datetime

    from wizard.models import (
        Note,
        NoteType,
        Task,
        TaskCategory,
        TaskPriority,
        TaskStatus,
        WizardSession,
    )
    from wizard.repositories import find_latest_session_with_notes

    s1 = WizardSession(created_at=datetime.datetime(2026, 4, 1))
    s2 = WizardSession(created_at=datetime.datetime(2026, 4, 5))
    s3 = WizardSession(created_at=datetime.datetime(2026, 4, 10))  # most recent but no notes
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.HIGH,
                category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()

    n1 = Note(task_id=task.id, session_id=s1.id, note_type=NoteType.INVESTIGATION, content="a")
    n2 = Note(task_id=task.id, session_id=s2.id, note_type=NoteType.INVESTIGATION, content="b")
    db_session.add_all([n1, n2])
    db_session.flush()

    result = find_latest_session_with_notes(db_session)
    assert result is not None
    assert result.id == s2.id  # s2 is most recent with notes; s3 has no notes


def test_count_investigations(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.repositories import NoteRepository

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    repo = NoteRepository()
    assert repo.count_investigations(db_session, task.id) == 0

    for i in range(2):
        db_session.add(Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content=f"inv {i}"))
    db_session.add(Note(task_id=task.id, note_type=NoteType.DECISION, content="dec"))
    db_session.flush()

    assert repo.count_investigations(db_session, task.id) == 2


def test_has_mental_model_false_when_none(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.repositories import NoteRepository

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    db_session.add(Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="inv"))
    db_session.flush()

    repo = NoteRepository()
    assert repo.has_mental_model(db_session, task.id) is False


def test_has_mental_model_true_when_present(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.repositories import NoteRepository

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    db_session.add(Note(
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="inv",
        mental_model="the system works like X",
    ))
    db_session.flush()

    repo = NoteRepository()
    assert repo.has_mental_model(db_session, task.id) is True
