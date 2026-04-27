"""Scenario: two sessions opened, notes saved under session B, resume session A."""


async def test_concurrent_sessions(mcp_client, seed_task):
    task = await seed_task(name="Shared task")

    # Session A
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_a_id = r.structured_content["session_id"]

    # Session B (without ending A — A will be auto-closed)
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_b_id = r.structured_content["session_id"]
    assert session_b_id != session_a_id

    # Save note under session B
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Note from session B",
    })
    assert not r.is_error, r
    note_id = r.structured_content["note_id"]

    # Note appears in session B's note list
    r = await mcp_client.call_tool("get_session", {"session_id": session_b_id})
    assert not r.is_error, r
    assert any(n["id"] == note_id for n in r.structured_content["notes"])

    # End session B
    r = await mcp_client.call_tool("session_end", {
        "session_id": session_b_id,
        "summary": "Session B work", "intent": "test",
        "working_set": [task.id], "state_delta": "B done",
        "open_loops": [], "next_actions": [], "closure_status": "clean",
    })
    assert not r.is_error, r
