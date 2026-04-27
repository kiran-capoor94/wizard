"""Scenario: empty abandoned session, sampling fails, synthetic still works (0 notes)."""


async def test_auto_close_empty_session(mcp_client):
    # Session 1: start with NO notes (empty session)
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    sid1 = r.structured_content["session_id"]

    # Session 2: sampling fails (no handler in test client), synthetic has 0 notes
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    closed = r.structured_content["closed_sessions"]
    assert len(closed) == 1
    assert closed[0]["session_id"] == sid1
    assert closed[0]["closed_via"] == "synthetic"
    assert closed[0]["note_count"] == 0
