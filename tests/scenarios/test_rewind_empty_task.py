"""Scenario: rewind_task on a task with no notes."""


async def test_rewind_empty_task(mcp_client, seed_task):
    task = await seed_task(name="Brand new task")

    r = await mcp_client.call_tool("rewind_task", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["summary"]["total_notes"] == 0
    assert d["summary"]["duration_days"] == 0
    assert d["timeline"] == []
