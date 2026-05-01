"""Scenario: failure note type is accepted and persisted by save_note."""


async def test_failure_note_type_accepted(mcp_client, seed_task):
    task = await seed_task(name="Failure type task")
    await mcp_client.call_tool("session_start", {})

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "failure",
        "content": "Tried inline cache invalidation — caused thundering herd on cache miss.",
    })
    assert not r.is_error, r
    assert r.structured_content["note_id"] > 0
