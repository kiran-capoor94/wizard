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


async def test_task_index_note_hint_truncated_to_80_chars(mcp_client, seed_task):
    task = await seed_task(name="Hint task")
    await mcp_client.call_tool("session_start", {})
    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "investigation",
        "content": "A" * 200,
    })

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    open_tasks = r.structured_content["open_tasks"]
    entry = next(e for e in open_tasks if e["id"] == task.id)
    hint = entry["last_note_hint"]
    assert hint is not None
    assert len(hint) <= 80


async def test_task_index_notes_by_type_counts(mcp_client, seed_task):
    task = await seed_task(name="Counts task")
    await mcp_client.call_tool("session_start", {})

    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "investigation",
        "content": "First investigation finding at auth.py:42.",
    })
    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "investigation",
        "content": "Second investigation finding at config.py:88.",
    })
    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "decision",
        "content": "Decided to use Redis for session storage.",
    })

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    open_tasks = r.structured_content["open_tasks"]
    entry = next(e for e in open_tasks if e["id"] == task.id)
    assert entry["note_count"] == 3
    assert entry["notes_by_type"] == {"investigation": 2, "decision": 1}
