"""Scenario: session started, work done, session_end never called. New session starts."""


async def test_abandoned_session(mcp_client, seed_task):
    task = await seed_task(name="Debug memory leak")

    # Session 1: start, do work, DON'T end
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_1_id = r.structured_content["session_id"]

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Heap dump shows growing object count",
    })
    assert not r.is_error, r

    # Session 2: start fresh without ending session 1
    # (sampling unavailable in test client -> synthetic fallback)
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert r.structured_content["session_id"] != session_1_id

    # Session 1 was auto-closed with a synthetic summary
    closed = r.structured_content["closed_sessions"]
    assert len(closed) == 1
    assert closed[0]["session_id"] == session_1_id
    assert closed[0]["closed_via"] == "synthetic"
    assert closed[0]["summary"] is not None

    # Notes from session 1 are still accessible via task_start
    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    assert r.structured_content["compounding"] is True
    assert sum(r.structured_content["notes_by_type"].values()) >= 1
