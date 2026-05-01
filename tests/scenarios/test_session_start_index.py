"""Scenario: session_start returns compact TaskIndexEntry index, not full TaskContext."""


async def test_session_start_returns_task_index_entries(mcp_client, seed_task):
    await seed_task(name="Alpha task")
    await seed_task(name="Beta task")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    open_tasks = r.structured_content["open_tasks"]
    assert isinstance(open_tasks, list)
    assert len(open_tasks) >= 2

    entry = open_tasks[0]
    # Required index keys
    assert "id" in entry
    assert "name" in entry
    assert "note_count" in entry
    assert "notes_by_type" in entry
    assert "last_note_hint" in entry
    assert "stale_days" in entry
    # Must NOT contain the old full-content key
    assert "last_note_preview" not in entry
