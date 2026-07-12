"""Scenario: search() finds note and session content via the FTS5 index.

Regression coverage for a real bug: `drop_synthesis_columns` ran
batch_alter_table on `note` and `wizardsession`, which recreates those tables
under the hood and silently drops any trigger defined on them — including
note_fts_ai/ad/au and session_fts_ai/ad/au, the triggers that keep the search
index in sync. Restored by the `restore_fts_triggers` migration. Task and
meeting search were never affected (those tables were never batch-altered),
so this file focuses on the two entity types that broke.
"""


async def test_search_finds_note_content(mcp_client, seed_task):
    task = await seed_task(name="Search coverage task")
    await mcp_client.call_tool("session_start", {})

    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "The rate limiter drops requests silently above 100 req/s.",
    })

    r = await mcp_client.call_tool("search", {"query": "rate limiter drops requests"})
    assert not r.is_error, r
    results = r.structured_content["results"]
    assert any(item["entity_type"] == "note" for item in results), results


async def test_search_finds_session_summary(mcp_client):
    start = await mcp_client.call_tool("session_start", {})
    session_id = start.structured_content["session_id"]

    await mcp_client.call_tool("session_end", {
        "session_id": session_id,
        "summary": "Investigated the JWT expiry race condition in auth middleware.",
        "intent": "test",
        "working_set": [],
        "state_delta": "done",
        "open_loops": [],
        "next_actions": [],
        "closure_status": "clean",
    })

    r = await mcp_client.call_tool("search", {"query": "JWT expiry race condition"})
    assert not r.is_error, r
    results = r.structured_content["results"]
    assert any(item["entity_type"] == "session" for item in results), results


async def test_search_removes_deleted_note_from_index(mcp_client, seed_task, db_session):
    """The AFTER DELETE trigger must also fire — a deleted note shouldn't
    keep matching, which would indicate the trigger was recreated wrong.
    No delete_note MCP tool exists, so delete via the same isolated
    db_session mcp_client is patched to use (the trigger fires the same
    way regardless of code path — it's on the table, not the query)."""
    from sqlalchemy import text

    task = await seed_task(name="Delete trigger coverage task")
    await mcp_client.call_tool("session_start", {})

    save_result = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "UNIQUE_MARKER_FOR_DELETE_TRIGGER_TEST appears exactly once.",
    })
    note_id = save_result.structured_content["note_id"]

    found = await mcp_client.call_tool(
        "search", {"query": "UNIQUE_MARKER_FOR_DELETE_TRIGGER_TEST"}
    )
    assert any(
        item["entity_type"] == "note" for item in found.structured_content["results"]
    )

    db_session.execute(text("DELETE FROM note WHERE id = :id"), {"id": note_id})
    db_session.commit()

    gone = await mcp_client.call_tool(
        "search", {"query": "UNIQUE_MARKER_FOR_DELETE_TRIGGER_TEST"}
    )
    assert not any(
        item["entity_type"] == "note" for item in gone.structured_content["results"]
    )
