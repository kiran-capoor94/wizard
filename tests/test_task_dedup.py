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
async def test_create_task_dedup_skips_done_task(db_session, fake_ctx):
    """Dedup should not update a task that is already DONE."""
    from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus

    t_repo = TaskRepository()
    ts_repo = TaskStateRepository()
    security = SecurityService()

    # Create a done task directly
    done_task = Task(
        name="Original",
        status=TaskStatus.DONE,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        source_id="ENG-999",
    )
    db_session.add(done_task)
    db_session.flush()
    db_session.refresh(done_task)
    original_id = done_task.id

    # Try to dedup-update it via create_task
    result = await create_task(
        ctx=fake_ctx,
        name="Updated name",
        priority=TaskPriority.HIGH,
        category=TaskCategory.ISSUE,
        source_id="ENG-999",
        t_repo=t_repo,
        sec=security,
        t_state_repo=ts_repo,
    )

    assert result.task_id == original_id
    assert result.already_existed is True
    # Name should NOT have been updated
    refreshed = t_repo.get_by_id(db_session, original_id)
    assert refreshed.name == "Original"


@pytest.mark.asyncio
async def test_create_task_dedup_skips_archived_task(db_session, fake_ctx):
    """Dedup should not update a task that is ARCHIVED."""
    from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus

    t_repo = TaskRepository()
    ts_repo = TaskStateRepository()
    security = SecurityService()

    archived_task = Task(
        name="Archived work",
        status=TaskStatus.ARCHIVED,
        priority=TaskPriority.LOW,
        category=TaskCategory.ISSUE,
        source_id="ENG-888",
    )
    db_session.add(archived_task)
    db_session.flush()
    db_session.refresh(archived_task)
    original_id = archived_task.id

    result = await create_task(
        ctx=fake_ctx,
        name="New name attempt",
        priority=TaskPriority.HIGH,
        category=TaskCategory.ISSUE,
        source_id="ENG-888",
        t_repo=t_repo,
        sec=security,
        t_state_repo=ts_repo,
    )

    assert result.task_id == original_id
    assert result.already_existed is True
    refreshed = t_repo.get_by_id(db_session, original_id)
    assert refreshed.name == "Archived work"


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
