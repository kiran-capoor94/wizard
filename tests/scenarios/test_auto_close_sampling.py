"""Scenario: abandoned session is auto-closed inline with synthetic summary.

Sampling via ctx.sample() is not used in close_recent_abandoned — it deadlocks
the stdio transport. All inline auto-closes use the synthetic summary path.
"""


async def test_auto_close_uses_synthetic_summary(mcp_client, seed_task):
    task = await seed_task(name="Debug memory leak")

    # Session 1: start, save a note, DON'T end
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    sid1 = r.structured_content["session_id"]

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Heap dump shows growing object count",
    })
    assert not r.is_error, r

    # Session 2 auto-closes session 1 inline using synthetic summary (no sampling)
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert r.structured_content["session_id"] != sid1

    closed = r.structured_content["closed_sessions"]
    assert len(closed) == 1
    assert closed[0]["session_id"] == sid1
    assert closed[0]["closed_via"] == "synthetic"
    assert closed[0]["note_count"] >= 1
    assert task.id in closed[0]["task_ids"]
