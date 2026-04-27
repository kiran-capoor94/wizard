"""Scenario: create task from meeting, verify linkage in get_meeting."""


async def test_meeting_to_task_linkage(mcp_client):
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    # Ingest meeting
    r = await mcp_client.call_tool("ingest_meeting", {
        "title": "Sprint Planning", "content": "Need to fix auth flow",
    })
    assert not r.is_error, r
    meeting_id = r.structured_content["meeting_id"]

    # Create task linked to meeting
    r = await mcp_client.call_tool("create_task", {
        "name": "Fix auth flow", "priority": "high", "category": "bug",
        "meeting_id": meeting_id,
    })
    assert not r.is_error, r
    task_id = r.structured_content["task_id"]

    # get_meeting should show linked task
    r = await mcp_client.call_tool("get_meeting", {"meeting_id": meeting_id})
    assert not r.is_error, r
    assert any(t["id"] == task_id for t in r.structured_content["open_tasks"])

    # Mark task done -- should no longer appear in open_tasks
    r = await mcp_client.call_tool("update_task", {"task_id": task_id, "status": "done"})
    assert not r.is_error, r

    r = await mcp_client.call_tool("get_meeting", {"meeting_id": meeting_id})
    assert not r.is_error, r
    assert not any(t["id"] == task_id for t in r.structured_content["open_tasks"])
