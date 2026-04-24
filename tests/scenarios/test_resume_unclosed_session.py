"""Scenario: resume a session that was never cleanly ended."""


async def test_resume_unclosed_session(mcp_client, seed_task):
    task = await seed_task(name="Unclosed session task")

    # Start session, do work, DON'T end
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Partial work before crash",
    })
    assert not r.is_error, r

    # Resume the unclosed session directly
    r = await mcp_client.call_tool("resume_session", {"session_id": session_id})
    assert not r.is_error, r
    d = r.structured_content

    # Auto-close writes session_state with closure_status='interrupted' for the abandoned session
    assert d["session_state"]["closure_status"] == "interrupted"
    assert d["resumed_from_session_id"] == session_id
    assert d["continued_from_id"] == session_id
    # Prior notes are still returned
    assert len(d["prior_notes"]) > 0
