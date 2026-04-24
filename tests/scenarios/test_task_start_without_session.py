"""Scenario: calling task_start and save_note without session_start."""


async def test_task_start_without_session(mcp_client, seed_task):
    """task_start works without a session -- it doesn't require one."""
    task = await seed_task(name="Orphan task")

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    assert r.structured_content["task"]["id"] == task.id


async def test_save_note_without_session(mcp_client, seed_task):
    """save_note without session_start: note is saved and retrievable."""
    task = await seed_task(name="Orphan task for notes")

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Working without a session",
    })
    assert not r.is_error, r
    note_id = r.structured_content["note_id"]
    assert note_id is not None

    # Note is retrievable via task_start
    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    assert any(n["id"] == note_id for n in r.structured_content["prior_notes"])
