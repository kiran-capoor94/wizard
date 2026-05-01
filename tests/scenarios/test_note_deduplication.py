"""Scenario: saving the exact same note twice deduplicates by content hash."""


async def test_duplicate_save_returns_was_duplicate_false_on_first(mcp_client, seed_task):
    task = await seed_task(name="Dedup task")
    await mcp_client.call_tool("session_start", {})

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "investigation",
        "content": "Found race condition in auth middleware at middleware.py:42.",
    })
    assert not r.is_error, r
    assert r.structured_content["was_duplicate"] is False
