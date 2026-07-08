"""Scenario: session_end truncates structured-state fields at SESSION_FIELD_MAX_CHARS.

compress() used to be the only mechanical backstop on these free-text fields;
now that it's removed, an explicit cap replaces it so a verbose or runaway
intent/state_delta/open_loop/next_action can't grow the stored session_state
JSON unbounded.
"""

from wizard.schemas import SESSION_FIELD_MAX_CHARS


async def test_session_end_truncates_oversized_fields(mcp_client):
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]

    oversized = "x" * (SESSION_FIELD_MAX_CHARS + 500)

    end_result = await mcp_client.call_tool("session_end", {
        "session_id": session_id,
        "summary": "Testing field length caps",
        "intent": oversized,
        "working_set": [],
        "state_delta": oversized,
        "open_loops": [oversized],
        "next_actions": [oversized],
        "closure_status": "clean",
    })
    assert not end_result.is_error, end_result

    resume = await mcp_client.call_tool("resume_session", {"session_id": session_id})
    assert not resume.is_error, resume
    state = resume.structured_content["session_state"]

    assert len(state["intent"]) == SESSION_FIELD_MAX_CHARS
    assert len(state["state_delta"]) == SESSION_FIELD_MAX_CHARS
    assert len(state["open_loops"][0]) == SESSION_FIELD_MAX_CHARS
    assert len(state["next_actions"][0]) == SESSION_FIELD_MAX_CHARS
