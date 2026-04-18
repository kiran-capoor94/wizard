"""Tests for source_id dedup and status validation in create_task."""

import pytest

from wizard.models import TaskCategory, TaskPriority
from wizard.repositories import TaskRepository, TaskStateRepository
from wizard.security import SecurityService
from wizard.tools.task_tools import create_task


@pytest.mark.asyncio
async def test_create_task_dedup_by_source_id(db_session, fake_ctx):
    """Second create_task with same source_id updates and returns already_existed=True."""
    t_repo = TaskRepository()
    ts_repo = TaskStateRepository()
    security = SecurityService()

    first = await create_task(
        ctx=fake_ctx,
        name="Fix login bug",
        priority=TaskPriority.HIGH,
        category=TaskCategory.ISSUE,
        source_id="ENG-123",
        t_repo=t_repo,
        sec=security,
        t_state_repo=ts_repo,
    )
    second = await create_task(
        ctx=fake_ctx,
        name="Fix login bug — updated",
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        source_id="ENG-123",
        t_repo=t_repo,
        sec=security,
        t_state_repo=ts_repo,
    )

    assert first.task_id == second.task_id
    assert second.already_existed is True
    task = t_repo.get_by_id(db_session, first.task_id)
    assert task.name == "Fix login bug — updated"


@pytest.mark.asyncio
async def test_create_task_no_source_id_always_creates(db_session, fake_ctx):
    """Tasks without source_id always create new records."""
    t_repo = TaskRepository()
    ts_repo = TaskStateRepository()
    security = SecurityService()

    first = await create_task(
        ctx=fake_ctx,
        name="Ad-hoc task",
        priority=TaskPriority.LOW,
        category=TaskCategory.ISSUE,
        t_repo=t_repo,
        sec=security,
        t_state_repo=ts_repo,
    )
    second = await create_task(
        ctx=fake_ctx,
        name="Ad-hoc task",
        priority=TaskPriority.LOW,
        category=TaskCategory.ISSUE,
        t_repo=t_repo,
        sec=security,
        t_state_repo=ts_repo,
    )

    assert first.task_id != second.task_id
    assert second.already_existed is False


@pytest.mark.asyncio
async def test_create_task_rejects_unknown_status(db_session, fake_ctx):
    """create_task raises ValueError for unknown status values."""
    t_repo = TaskRepository()
    ts_repo = TaskStateRepository()
    security = SecurityService()

    with pytest.raises(ValueError, match="Invalid status"):
        await create_task(
            ctx=fake_ctx,
            name="Task",
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.ISSUE,
            status="in progress",  # invalid — must be "in_progress"
            t_repo=t_repo,
            sec=security,
            t_state_repo=ts_repo,
        )
