"""Scenario: resume_session with no prior sessions, and with nonexistent session_id."""


async def test_cold_resume_no_sessions(mcp_client):
    """resume_session() with no args when no sessions exist."""
    r = await mcp_client.call_tool("resume_session", {})
    assert r.is_error


async def test_cold_resume_nonexistent_session(mcp_client):
    """resume_session(session_id=999) for a session that doesn't exist."""
    r = await mcp_client.call_tool("resume_session", {"session_id": 999})
    assert r.is_error
