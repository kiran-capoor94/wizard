"""Scenario: create task, update, save notes, rewind."""


async def test_task_creation_flow(mcp_client):
    # Start session
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    # 1. create_task
    r = await mcp_client.call_tool("create_task", {
        "name": "Fix login bug", "priority": "high", "category": "bug",
    })
    assert not r.is_error, r
    task_id = r.structured_content["task_id"]
    assert task_id is not None

    # 2. update_task -- status to in_progress
    r = await mcp_client.call_tool("update_task", {
        "task_id": task_id, "status": "in_progress",
    })
    assert not r.is_error, r
    assert "status" in r.structured_content["updated_fields"]

    # 3. save_note
    r = await mcp_client.call_tool("save_note", {
        "task_id": task_id, "note_type": "decision", "content": "Going with OAuth2",
    })
    assert not r.is_error, r

    # 4. update_task -- done
    r = await mcp_client.call_tool("update_task", {
        "task_id": task_id, "status": "done",
    })
    assert not r.is_error, r
    assert "status" in r.structured_content["updated_fields"]

    # 5. rewind_task -- should show full timeline
    r = await mcp_client.call_tool("rewind_task", {"task_id": task_id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["summary"]["total_notes"] == 1
    assert len(d["timeline"]) == 1
    assert d["timeline"][0]["note_type"] == "decision"
