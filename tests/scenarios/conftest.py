"""Scenario-specific fixtures: seed data helpers."""

from types import SimpleNamespace

import pytest

from wizard.models import TaskCategory, TaskPriority
from wizard.tools.task_tools import create_task


@pytest.fixture
def seed_task(fake_ctx, task_repo, security, task_state_repo):
    """Factory fixture: creates a task via the create_task tool."""

    async def _create(
        name: str = "Test task",
        priority: TaskPriority = TaskPriority.MEDIUM,
        category: TaskCategory = TaskCategory.ISSUE,
        status: str = "todo",
        source_id: str | None = None,
        source_url: str | None = None,
    ) -> SimpleNamespace:
        resp = await create_task(
            ctx=fake_ctx,
            name=name,
            priority=priority,
            category=category,
            status=status,
            source_id=source_id,
            source_url=source_url,
            t_repo=task_repo,
            sec=security,
            t_state_repo=task_state_repo,
        )
        return SimpleNamespace(id=resp.task_id)

    return _create
