"""Scenario: what_am_i_missing signals evolve as notes are added."""


async def test_signal_progression(mcp_client, seed_task):
    task = await seed_task(name="Signal test task")
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    def signal_types(d):
        return {s["type"] for s in d["signals"]}

    # 1. No notes -> no_context signal
    r = await mcp_client.call_tool("what_am_i_missing", {"task_id": task.id})
    assert not r.is_error, r
    assert "no_context" in signal_types(r.structured_content)

    # 2. One investigation -> low_context + no_decisions
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation", "content": "Looking into it",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("what_am_i_missing", {"task_id": task.id})
    assert not r.is_error, r
    types = signal_types(r.structured_content)
    assert "no_context" not in types
    assert "no_decisions" in types

    # 3. 4+ investigations, no decision -> analysis_loop
    for i in range(3):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id, "note_type": "investigation",
            "content": f"Investigation round {i+2}",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("what_am_i_missing", {"task_id": task.id})
    assert not r.is_error, r
    assert "analysis_loop" in signal_types(r.structured_content)

    # 4. Decision with mental model -> analysis_loop and no_decisions gone
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "decision",
        "content": "Going with approach B",
        "mental_model": "Root cause is in the auth middleware",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("what_am_i_missing", {"task_id": task.id})
    assert not r.is_error, r
    types = signal_types(r.structured_content)
    assert "analysis_loop" not in types
    assert "no_decisions" not in types
    assert "no_model" not in types
