"""Scenario-specific fixtures: seed data helpers."""

from types import SimpleNamespace

import pytest

from wizard.models import TaskCategory, TaskPriority


@pytest.fixture
def seed_task(mcp_client):
    """Factory fixture: creates a task via the MCP pipeline."""

    async def _create(
        name: str = "Test task",
        priority: TaskPriority = TaskPriority.MEDIUM,
        category: TaskCategory = TaskCategory.ISSUE,
        status: str = "todo",
        source_id: str | None = None,
        source_url: str | None = None,
    ) -> SimpleNamespace:
        args: dict = {"name": name, "priority": priority.value, "category": category.value}
        if source_id is not None:
            args["source_id"] = source_id
        if source_url is not None:
            args["source_url"] = source_url
        result = await mcp_client.call_tool("create_task", args)
        assert not result.is_error, f"seed_task failed: {result}"
        return SimpleNamespace(id=result.structured_content["task_id"])

    return _create
