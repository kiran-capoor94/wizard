"""Scenario: ingest meeting, get it, save summary, test dedup."""


async def test_meeting_ingestion(mcp_client):
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    # 1. ingest_meeting
    r = await mcp_client.call_tool("ingest_meeting", {
        "title": "Sprint Planning",
        "content": "Discussed Q3 priorities and assignments",
        "source_id": "krisp-abc123",
        "source_url": "https://krisp.ai/meetings/abc123",
    })
    assert not r.is_error, r
    meeting_id = r.structured_content["meeting_id"]
    assert meeting_id is not None
    assert r.structured_content["already_existed"] is False

    # 2. get_meeting
    r = await mcp_client.call_tool("get_meeting", {"meeting_id": meeting_id})
    assert not r.is_error, r
    assert r.structured_content["title"] == "Sprint Planning"
    assert r.structured_content["already_summarised"] is False

    # 3. save_meeting_summary
    r = await mcp_client.call_tool("save_meeting_summary", {
        "meeting_id": meeting_id, "summary": "Agreed on Q3 priorities",
    })
    assert not r.is_error, r
    assert r.structured_content["note_id"] is not None

    # 4. get_meeting again -- should be summarised now
    r = await mcp_client.call_tool("get_meeting", {"meeting_id": meeting_id})
    assert not r.is_error, r
    assert r.structured_content["already_summarised"] is True

    # 5. ingest same meeting again (dedup by source_id)
    r = await mcp_client.call_tool("ingest_meeting", {
        "title": "Sprint Planning (updated)",
        "content": "Updated content",
        "source_id": "krisp-abc123",
    })
    assert not r.is_error, r
    assert r.structured_content["already_existed"] is True
    assert r.structured_content["meeting_id"] == meeting_id
