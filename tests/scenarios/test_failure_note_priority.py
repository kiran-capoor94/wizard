import pytest


@pytest.mark.asyncio
async def test_failure_notes_sort_before_decisions_in_task_start(mcp_client, seed_task):
    task = await seed_task(name="Priority ordering task")
    await mcp_client.call_tool("session_start", {})

    # Save a decision note first (older)
    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "decision",
        "content": "Decided to use Redis for session storage.",
    })

    # Save a failure note second (newer)
    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "failure",
        "content": "Tried in-memory LRU cache — evicted under load, caused 503s.",
    })

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r

    prior_notes = r.structured_content["prior_notes"]
    assert len(prior_notes) == 2
    # failure note must appear before decision note regardless of creation order
    types = [n["note_type"] for n in prior_notes]
    assert types.index("failure") < types.index("decision")


@pytest.mark.asyncio
async def test_key_notes_capped_at_five_with_many_high_priority_notes(mcp_client, seed_task):
    """Test that _select_key_notes enforces cap across all tiers (failure + decision).

    With 3 failure + 3 decision notes, the total is 6 high-priority notes.
    The cap is 5, so the function should truncate to 5 notes.
    Also verify that failure notes come before decision notes.
    """
    task = await seed_task(name="Cap overflow task")
    await mcp_client.call_tool("session_start", {})

    # 3 failure notes + 3 decision notes = 6 high-priority notes, but cap is 5
    for i in range(3):
        await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "failure",
            "content": f"Failure {i}: tried approach {i} and it broke at service.py:{i}.",
        })
    for i in range(3):
        await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "decision",
            "content": f"Decision {i}: chose option {i} for module_{i}.py.",
        })

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    prior_notes = r.structured_content["prior_notes"]

    # Cap enforcement: should return at most 5 notes
    assert len(prior_notes) <= 5, f"Expected <= 5 notes, got {len(prior_notes)}: {[n['note_type'] for n in prior_notes]}"

    # Tier priority: failure notes should come before decision notes
    types = [n["note_type"] for n in prior_notes]
    failure_indices = [i for i, t in enumerate(types) if t == "failure"]
    decision_indices = [i for i, t in enumerate(types) if t == "decision"]
    if failure_indices and decision_indices:
        assert max(failure_indices) < min(decision_indices), \
            f"Failure notes should come before decision notes. Got: {types}"
