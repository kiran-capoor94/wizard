"""Scenario: update_task with no fields, and with invalid due_date."""

import pytest
from fastmcp.exceptions import ToolError

from wizard.tools.task_tools import update_task


@pytest.mark.asyncio
async def test_update_task_no_fields(
    db_session, fake_ctx, task_repo, task_state_repo, security,
    seed_task,
):
    task = seed_task(name="Update me")
    with pytest.raises(ToolError, match="At least one field"):
        await update_task(
            ctx=fake_ctx, task_id=task.id,
            t_repo=task_repo, sec=security,
            t_state_repo=task_state_repo,
        )


@pytest.mark.asyncio
async def test_update_task_invalid_due_date(
    db_session, fake_ctx, task_repo, task_state_repo, security,
    seed_task,
):
    task = seed_task(name="Bad date task")
    with pytest.raises(ToolError, match="ISO 8601"):
        await update_task(
            ctx=fake_ctx, task_id=task.id, due_date="not-a-date",
            t_repo=task_repo, sec=security,
            t_state_repo=task_state_repo,
        )
