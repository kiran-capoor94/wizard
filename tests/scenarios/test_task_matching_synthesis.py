"""Scenario: task matching assigns task_id to synthesised notes."""

import pytest


@pytest.mark.asyncio
async def test_get_open_tasks_compact_returns_id_name_pairs(
    db_session, task_repo, seed_task
):
    task = await seed_task(name="Fix auth bug")
    results = task_repo.get_open_tasks_compact(db_session)
    assert len(results) == 1
    assert results[0] == (task.id, "Fix auth bug")


@pytest.mark.asyncio
async def test_get_open_tasks_compact_excludes_done_tasks(
    db_session, task_repo, seed_task
):
    await seed_task(name="Done task", status="done")
    await seed_task(name="Open task", status="todo")
    results = task_repo.get_open_tasks_compact(db_session)
    names = [r[1] for r in results]
    assert "Open task" in names
    assert "Done task" not in names
