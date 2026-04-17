from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockContext, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------


async def test_update_task_updates_single_field(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_due_date.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            due_date="2026-04-17T14:00:00Z",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.task_id == task.id
    assert "due_date" in result.updated_fields
    assert len(result.updated_fields) == 1

    db_session.refresh(task)
    assert task.due_date is not None


async def test_update_task_updates_multiple_fields(db_session):
    from wizard.models import Task, TaskPriority, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_priority.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert set(result.updated_fields) == {"status", "priority"}
    assert result.task_state_updated is True

    db_session.refresh(task)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.priority == TaskPriority.HIGH


async def test_update_task_raises_when_no_fields(db_session):
    from fastmcp.exceptions import ToolError

    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        with pytest.raises(ToolError, match="At least one field"):
            await update_task(
                ctx,
                task_id=task.id,
                t_repo=TaskRepository(),
                sec=SecurityService(),
                t_state_repo=TaskStateRepository(),
                wb=MagicMock(),
            )


async def test_update_task_done_elicits_outcome(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    task = Task(name="test", status=TaskStatus.IN_PROGRESS, notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.append_task_outcome.return_value = WriteBackStatus(ok=True)

    ctx = MockContext(elicit_response="Completed successfully")
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.DONE,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    wb_mock.append_task_outcome.assert_called_once()


async def test_update_task_done_without_notion_id_skips_elicit(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    task = Task(name="test", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    ctx = MockContext(elicit_response="should not be used")
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.DONE,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    wb_mock.append_task_outcome.assert_not_called()


async def test_update_task_invalid_due_date_format(db_session):
    from fastmcp.exceptions import ToolError

    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        with pytest.raises(ToolError, match="Invalid due_date format"):
            await update_task(
                ctx,
                task_id=task.id,
                due_date="not-a-date",
                t_repo=TaskRepository(),
                sec=SecurityService(),
                t_state_repo=TaskStateRepository(),
                wb=MagicMock(),
            )


async def test_update_task_name_is_scrubbed(db_session):
    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await update_task(
            ctx,
            task_id=task.id,
            name="john@example.com reported bug",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=MagicMock(),
        )

    db_session.refresh(task)
    assert "john@example.com" not in task.name
    assert "[EMAIL_1]" in task.name


async def test_update_task_due_date_writeback(db_session):
    from wizard.models import Task
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_due_date.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            due_date="2026-04-17T14:00:00Z",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.due_date_writeback is not None
    assert result.due_date_writeback.ok is True
    wb_mock.push_task_due_date.assert_called_once()


async def test_update_task_priority_writeback(db_session):
    from wizard.models import Task, TaskPriority
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_priority.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            priority=TaskPriority.HIGH,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.priority_writeback is not None
    assert result.priority_writeback.ok is True
    wb_mock.push_task_priority.assert_called_once()


async def test_update_task_notion_id(db_session):
    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            notion_id="notion-456",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=MagicMock(),
        )

    assert "notion_id" in result.updated_fields
    db_session.refresh(task)
    assert task.notion_id == "notion-456"


async def test_update_task_source_url(db_session):
    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            source_url="https://github.com/org/repo/issues/123",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=MagicMock(),
        )

    assert "source_url" in result.updated_fields
    db_session.refresh(task)
    assert task.source_url == "https://github.com/org/repo/issues/123"


async def test_update_task_outcome_writeback_called_when_elicited(db_session):
    """Outcome writeback must be called when elicitation returns text."""
    import datetime

    from wizard.models import Task, TaskCategory, TaskPriority, TaskState, TaskStatus
    from wizard.tools import update_task

    task = Task(
        name="Fix auth",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        notion_id="notion-page-123",
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    state = TaskState(
        task_id=task.id,
        note_count=0,
        decision_count=0,
        last_touched_at=datetime.datetime.now(),
        stale_days=0,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext(elicit_response="Shipped the fix.")
    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = MagicMock(ok=True, error=None)
    wb_mock.push_task_status_to_notion.return_value = MagicMock(ok=True, error=None, page_id="notion-page-123")
    wb_mock.append_task_outcome.return_value = MagicMock(ok=True, error=None)

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.DONE,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    wb_mock.append_task_outcome.assert_called_once()
    call_args = wb_mock.append_task_outcome.call_args
    assert "Shipped the fix." in call_args[0][1]
    assert result.updated_fields == ["status"]
