"""Scenario: failure notes sort first in task_start prior_notes, before decisions."""


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
