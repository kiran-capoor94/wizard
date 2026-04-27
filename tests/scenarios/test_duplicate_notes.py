"""Scenario: saving the exact same note twice -- both should persist."""


async def test_duplicate_notes(mcp_client, seed_task):
    task = await seed_task(name="Dupe notes task")
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    content = "Found the bug in auth"
    r1 = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation", "content": content,
    })
    assert not r1.is_error, r1
    r2 = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation", "content": content,
    })
    assert not r2.is_error, r2
    assert r1.structured_content["note_id"] != r2.structured_content["note_id"]

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    assert sum(r.structured_content["notes_by_type"].values()) == 2
