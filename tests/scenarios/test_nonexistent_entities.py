"""Scenario: tools return errors when given nonexistent IDs."""


async def test_task_start_nonexistent(mcp_client):
    r = await mcp_client.call_tool("task_start", {"task_id": 9999})
    assert r.is_error


async def test_save_note_nonexistent(mcp_client):
    r = await mcp_client.call_tool("save_note", {
        "task_id": 9999, "note_type": "investigation", "content": "test",
    })
    assert r.is_error


async def test_update_task_nonexistent(mcp_client):
    r = await mcp_client.call_tool("update_task", {"task_id": 9999, "status": "done"})
    assert r.is_error


async def test_rewind_task_nonexistent(mcp_client):
    r = await mcp_client.call_tool("rewind_task", {"task_id": 9999})
    assert r.is_error


async def test_what_am_i_missing_nonexistent(mcp_client):
    r = await mcp_client.call_tool("what_am_i_missing", {"task_id": 9999})
    assert r.is_error


async def test_session_end_nonexistent(mcp_client):
    r = await mcp_client.call_tool("session_end", {
        "session_id": 9999, "summary": "test", "intent": "test",
        "working_set": [], "state_delta": "test",
        "open_loops": [], "next_actions": [], "closure_status": "clean",
    })
    assert r.is_error


async def test_get_meeting_nonexistent(mcp_client):
    r = await mcp_client.call_tool("get_meeting", {"meeting_id": 9999})
    assert r.is_error


async def test_save_meeting_summary_nonexistent(mcp_client):
    r = await mcp_client.call_tool("save_meeting_summary", {
        "meeting_id": 9999, "summary": "test",
    })
    assert r.is_error
