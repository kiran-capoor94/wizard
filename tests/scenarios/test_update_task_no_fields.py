"""Scenario: update_task with no fields, and with invalid due_date."""
import pytest


async def test_update_task_no_fields(mcp_client, seed_task):
    task = await seed_task(name="Update me")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id})
    assert r.is_error


async def test_update_task_invalid_due_date(mcp_client, seed_task):
    task = await seed_task(name="Bad date task")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id, "due_date": "not-a-date"})
    assert r.is_error


async def test_update_task_empty_due_date_is_noop(mcp_client, seed_task):
    task = await seed_task(name="Empty date task")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": "blocked", "due_date": ""})
    assert not r.is_error


@pytest.mark.parametrize("alias", ["completed", "complete", "finished", "finish"])
async def test_update_task_status_done_aliases(mcp_client, seed_task, alias):
    task = await seed_task(name="Alias task")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": alias})
    assert not r.is_error
    stored = await mcp_client.call_tool("get_task", {"task_id": task.id})
    assert stored.structured_content["task"]["status"] == "done"


async def test_update_task_status_open_alias(mcp_client, seed_task):
    task = await seed_task(name="Open alias task")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": "open"})
    assert not r.is_error
    stored = await mcp_client.call_tool("get_task", {"task_id": task.id})
    assert stored.structured_content["task"]["status"] == "todo"


@pytest.mark.parametrize("alias,expected", [
    ("wip", "in_progress"),
    ("doing", "in_progress"),
    ("pending", "todo"),
    ("inactive", "archived"),
    ("COMPLETED", "done"),  # case-insensitive
])
async def test_update_task_status_remaining_aliases(mcp_client, seed_task, alias, expected):
    task = await seed_task(name=f"Alias {alias} task")
    r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": alias})
    assert not r.is_error
    stored = await mcp_client.call_tool("get_task", {"task_id": task.id})
    assert stored.structured_content["task"]["status"] == expected


async def test_create_task_status_alias(mcp_client):
    r = await mcp_client.call_tool("create_task", {
        "name": "Aliased status task",
        "priority": "medium",
        "category": "issue",
        "status": "completed",
    })
    assert not r.is_error
    task_id = r.structured_content["task_id"]
    stored = await mcp_client.call_tool("get_task", {"task_id": task_id})
    assert stored.structured_content["task"]["status"] == "done"
