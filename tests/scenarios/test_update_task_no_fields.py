"""Scenario: update_task with no fields, and with invalid due_date."""


async def test_update_task_no_fields(mcp_client, seed_task):
    task = await seed_task(name="Update me")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id})
    assert r.is_error


async def test_update_task_invalid_due_date(mcp_client, seed_task):
    task = await seed_task(name="Bad date task")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id, "due_date": "not-a-date"})
    assert r.is_error
