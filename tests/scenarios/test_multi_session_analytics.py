"""Scenario: run multiple sessions, verify state across them via query tools."""


async def test_multi_session_analytics(mcp_client, seed_task):
    task1 = await seed_task(name="Task A")
    task2 = await seed_task(name="Task B", source_id="unique-b")

    session_ids = []
    note_counts = [3, 2, 1]  # notes per session

    for i, count in enumerate(note_counts):
        r = await mcp_client.call_tool("session_start", {})
        assert not r.is_error, r
        session_ids.append(r.structured_content["session_id"])

        target_task = task1 if i % 2 == 0 else task2
        for j in range(count):
            r = await mcp_client.call_tool("save_note", {
                "task_id": target_task.id, "note_type": "investigation",
                "content": f"Session {i+1} note {j+1}",
            })
            assert not r.is_error, r

        r = await mcp_client.call_tool("session_end", {
            "session_id": session_ids[-1],
            "summary": f"Session {i+1} done", "intent": "test",
            "working_set": [target_task.id], "state_delta": "done",
            "open_loops": [], "next_actions": [], "closure_status": "clean",
        })
        assert not r.is_error, r

    # Verify: 3 sessions visible via get_sessions
    r = await mcp_client.call_tool("get_sessions", {})
    assert not r.is_error, r
    assert r.structured_content["total_returned"] == 3

    # Verify: notes per session (task notes + session_summary from session_end)
    for sid, expected_task_notes in zip(session_ids, note_counts, strict=True):
        r = await mcp_client.call_tool("get_session", {"session_id": sid})
        assert not r.is_error, r
        notes = r.structured_content["notes"]
        task_notes = [n for n in notes if n["note_type"] != "session_summary"]
        summary_notes = [n for n in notes if n["note_type"] == "session_summary"]
        assert len(task_notes) == expected_task_notes
        assert len(summary_notes) == 1
