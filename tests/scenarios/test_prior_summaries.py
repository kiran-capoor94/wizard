"""Scenario: session_start returns prior_summaries from recently closed sessions."""


async def test_prior_summaries_empty_on_first_session(mcp_client):
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert r.structured_content["prior_summaries"] == []


async def test_prior_summaries_contains_most_recent_closed_session(mcp_client):
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    sid1 = r.structured_content["session_id"]

    r = await mcp_client.call_tool("session_end", {
        "session_id": sid1,
        "summary": "Investigated the auth token expiry bug and found the root cause",
        "intent": "debug", "working_set": [], "state_delta": "found root cause",
        "open_loops": [], "next_actions": [], "closure_status": "clean",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    d = r.structured_content
    assert len(d["prior_summaries"]) == 1
    assert d["prior_summaries"][0]["session_id"] == sid1
    assert "auth token" in d["prior_summaries"][0]["summary"]


async def test_prior_summaries_capped_at_three(mcp_client):
    for i in range(5):
        r = await mcp_client.call_tool("session_start", {})
        assert not r.is_error, r
        sid = r.structured_content["session_id"]
        r = await mcp_client.call_tool("session_end", {
            "session_id": sid,
            "summary": f"Session {i + 1} completed work on the feature",
            "intent": "work", "working_set": [], "state_delta": "",
            "open_loops": [], "next_actions": [], "closure_status": "clean",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert len(r.structured_content["prior_summaries"]) == 3


async def test_prior_summaries_task_ids_from_working_set(mcp_client, seed_task):
    task = await seed_task(name="Auth bug fix")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    sid1 = r.structured_content["session_id"]

    r = await mcp_client.call_tool("session_end", {
        "session_id": sid1, "summary": "Fixed the auth bug", "intent": "fix",
        "working_set": [task.id], "state_delta": "done",
        "open_loops": [], "next_actions": [], "closure_status": "clean",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert r.structured_content["prior_summaries"][0]["task_ids"] == [task.id]
