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
