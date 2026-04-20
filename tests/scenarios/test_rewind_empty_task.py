"""Scenario: rewind_task on a task with no notes."""

import pytest

from wizard.tools.task_tools import rewind_task


@pytest.mark.asyncio
async def test_rewind_empty_task(db_session, fake_ctx, note_repo, seed_task):
    task = await seed_task(name="Brand new task")

    resp = await rewind_task(ctx=fake_ctx, task_id=task.id, n_repo=note_repo)
    assert resp.summary.total_notes == 0
    assert resp.summary.duration_days == 0
    assert resp.timeline == []
