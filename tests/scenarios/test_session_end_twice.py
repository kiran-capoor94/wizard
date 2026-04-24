"""Scenario: calling session_end twice on the same session."""


async def test_session_end_twice(mcp_client):
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]

    end_args = {
        "session_id": session_id, "summary": "First end", "intent": "test",
        "working_set": [], "state_delta": "done",
        "open_loops": [], "next_actions": [], "closure_status": "clean",
    }

    r1 = await mcp_client.call_tool("session_end", end_args)
    assert not r1.is_error, r1
    note_id_1 = r1.structured_content["note_id"]
    assert note_id_1 is not None

    # Second end on same session -- documents current behaviour
    # (currently succeeds and creates a second summary note)
    end_args["summary"] = "Second end"
    r2 = await mcp_client.call_tool("session_end", end_args)
    assert not r2.is_error, r2
    assert r2.structured_content["note_id"] != note_id_1
