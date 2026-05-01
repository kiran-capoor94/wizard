"""Scenario: session_start with non-UUID and malformed agent_session_ids."""
import pytest


@pytest.mark.parametrize("sid", [
    "session-2026-04-22-gemini-studio-free-tier",
    "f3112da5-5c78-4dc1-8dac281bc496",  # malformed UUID
    "some-arbitrary-agent-id-123",
])
async def test_session_start_non_uuid_id_succeeds(mcp_client, sid):
    r = await mcp_client.call_tool("session_start", {"agent_session_id": sid})
    assert not r.is_error, r
    assert r.structured_content["session_id"] is not None


@pytest.mark.parametrize("sid", [
    "../etc/passwd",
    "../../secrets",
    "foo/bar",
    "foo\\bar",
])
async def test_session_start_path_traversal_id_ignored(mcp_client, sid):
    r = await mcp_client.call_tool("session_start", {"agent_session_id": sid})
    assert not r.is_error, r
    assert r.structured_content["session_id"] is not None
