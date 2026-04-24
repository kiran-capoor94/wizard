"""Scenario: sampling fails, abandoned session is auto-closed with synthetic summary."""


async def test_auto_close_synthetic_fallback(mcp_client, seed_task):
    task = await seed_task(name="Fix auth bug")

    # Session 1: start, do work, DON'T end
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    sid1 = r.structured_content["session_id"]

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "decision", "content": "Switch to JWT tokens",
    })
    assert not r.is_error, r

    # Session 2: sampling fails (no handler in test client) -> synthetic fallback
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    closed = r.structured_content["closed_sessions"]
    assert len(closed) == 1
    assert closed[0]["session_id"] == sid1
    assert closed[0]["closed_via"] == "synthetic"
    assert "1 note(s)" in closed[0]["summary"]
    assert "1 task(s)" in closed[0]["summary"]
