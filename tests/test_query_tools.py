import pytest

from wizard.models import (
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskStatus,
    WizardSession,
)
from wizard.repositories import (
    NoteRepository,
    SessionRepository,
    TaskRepository,
    TaskStateRepository,
)
from wizard.schemas import SessionState
from wizard.tools.query_tools import get_session, get_sessions, get_task, get_tasks


@pytest.mark.asyncio
async def test_get_tasks_returns_empty_when_no_tasks(db_session):
    result = await get_tasks(
        t_repo=TaskRepository(), ts_repo=TaskStateRepository(), db=db_session,
    )
    assert result.items == []
    assert result.next_cursor is None
    assert result.total_returned == 0


@pytest.mark.asyncio
async def test_get_tasks_returns_tasks(db_session):
    task = Task(
        name="Fix auth", status=TaskStatus.TODO,
        priority=TaskPriority.HIGH, category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()

    result = await get_tasks(
        t_repo=TaskRepository(), ts_repo=TaskStateRepository(), db=db_session,
    )

    assert len(result.items) == 1
    assert result.items[0].name == "Fix auth"


@pytest.mark.asyncio
async def test_get_tasks_filters_by_status(db_session):
    t1 = Task(name="Open", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    t2 = Task(name="Done", status=TaskStatus.DONE, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    result = await get_tasks(
        status=["todo"],
        t_repo=TaskRepository(), ts_repo=TaskStateRepository(), db=db_session,
    )

    assert len(result.items) == 1
    assert result.items[0].name == "Open"


@pytest.mark.asyncio
async def test_get_tasks_pagination(db_session):
    for i in range(5):
        db_session.add(Task(
            name=f"Task {i}", status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE,
        ))
    db_session.flush()

    page1 = await get_tasks(
        limit=3, t_repo=TaskRepository(), ts_repo=TaskStateRepository(), db=db_session,
    )
    assert len(page1.items) == 3
    assert page1.next_cursor is not None

    page2 = await get_tasks(
        limit=3, cursor=page1.next_cursor,
        t_repo=TaskRepository(), ts_repo=TaskStateRepository(), db=db_session,
    )
    assert len(page2.items) == 2
    assert page2.next_cursor is None


@pytest.mark.asyncio
async def test_get_task_returns_notes(db_session):
    task = Task(name="My task", status=TaskStatus.TODO, priority=TaskPriority.LOW, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(note_type=NoteType.INVESTIGATION, content="Found the bug", task_id=task.id)
    db_session.add(note)
    db_session.flush()

    result = await get_task(
        task_id=task.id,
        t_repo=TaskRepository(), n_repo=NoteRepository(), db=db_session,
    )

    assert result.task.name == "My task"
    assert len(result.notes) == 1
    assert result.notes[0].content == "Found the bug"


@pytest.mark.asyncio
async def test_get_sessions_returns_empty(db_session):
    result = await get_sessions(s_repo=SessionRepository(), n_repo=NoteRepository(), db=db_session)
    assert result.items == []


@pytest.mark.asyncio
async def test_get_session_returns_state(db_session):
    state = SessionState(
        intent="Build feature X", working_set=[1, 2],
        state_delta="", open_loops=[], next_actions=[], closure_status="clean",
    )
    session = WizardSession(session_state=state.model_dump_json(), closed_by="user")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    result = await get_session(
        session_id=session.id,
        s_repo=SessionRepository(), n_repo=NoteRepository(), db=db_session,
    )

    assert result.session.id == session.id
    assert result.session_state.intent == "Build feature X"
