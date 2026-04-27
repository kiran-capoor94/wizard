"""Scenario: start, work, end, then resume from a new session."""


async def test_resume_session(mcp_client, seed_task):
    task = await seed_task(name="Investigate auth issue")

    # Session 1: start, save note, end
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_1_id = r.structured_content["session_id"]

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Found a suspicious pattern in the logs",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("session_end", {
        "session_id": session_1_id,
        "summary": "Investigated auth, found log pattern",
        "intent": "Investigation",
        "working_set": [task.id],
        "state_delta": "Found suspicious log pattern",
        "open_loops": ["Need to check prod logs"],
        "next_actions": ["Compare with staging"],
        "closure_status": "interrupted",
    })
    assert not r.is_error, r

    # Session 2: resume from session 1
    r = await mcp_client.call_tool("resume_session", {"session_id": session_1_id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["resumed_from_session_id"] == session_1_id
    assert d["session_id"] != session_1_id
    assert d["continued_from_id"] == session_1_id
    assert d["session_state"] is not None
    assert d["session_state"]["closure_status"] == "interrupted"
    assert len(d["session_state"]["open_loops"]) == 1
    assert len(d["prior_notes"]) > 0


async def test_resume_session_caps_prior_notes_per_task(mcp_client, seed_task):
    """resume_session must return at most 3 notes per task even when more exist."""
    task = await seed_task(name="Well-documented task")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]

    # Save 5 notes -- more than the 3-note cap
    for i in range(5):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id, "note_type": "investigation", "content": f"Finding {i}",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("session_end", {
        "session_id": session_id,
        "summary": "Investigated thoroughly", "intent": "Investigation",
        "working_set": [task.id], "state_delta": "Found 5 things",
        "open_loops": [], "next_actions": [], "closure_status": "clean",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("resume_session", {"session_id": session_id})
    assert not r.is_error, r
    d = r.structured_content

    assert len(d["prior_notes"]) == 1  # one task
    task_notes = d["prior_notes"][0]
    assert len(task_notes["notes"]) == 3  # capped at 3
    note_contents = [n["content"] for n in task_notes["notes"]]
    assert "Finding 4" in note_contents
    assert "Finding 3" in note_contents
    assert "Finding 2" in note_contents
