from unittest.mock import MagicMock, patch

from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


async def test_create_task_creates_and_links(db_session):
    from sqlmodel import select

    from wizard.models import Meeting, MeetingTasks, Task, TaskPriority, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import create_task

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(
        ok=True,
        page_id="notion-task-page-id",
    )

    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    meeting_id = meeting.id

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskStateRepository
        from wizard.security import SecurityService
        result = await create_task(
            ctx,
            name="Fix john@example.com auth bug",
            priority=TaskPriority.HIGH,
            meeting_id=meeting_id,
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.task_id is not None
    assert result.notion_write_back.ok is True
    task = db_session.get(Task, result.task_id)
    assert "john@example.com" not in task.name
    assert task.status == TaskStatus.TODO

    link = db_session.exec(
        select(MeetingTasks).where(
            MeetingTasks.task_id == task.id,
            MeetingTasks.meeting_id == meeting_id,
        )
    ).first()
    assert link is not None


async def test_create_task_creates_paired_task_state(db_session):
    from wizard.models import TaskState
    from wizard.schemas import WriteBackStatus
    from wizard.tools import create_task

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(ok=True)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskStateRepository
        from wizard.security import SecurityService
        response = await create_task(
            ctx,
            name="new task",
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    state = db_session.get(TaskState, response.task_id)
    assert state is not None
    assert state.note_count == 0
    assert state.decision_count == 0


async def test_create_task_with_active_session(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import create_task

    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(
        ok=False, error="no notion"
    )
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskStateRepository
        from wizard.security import SecurityService
        result = await create_task(
            ctx,
            name="new task",
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.task_id is not None
