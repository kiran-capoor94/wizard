"""Scenario: PII in note content gets scrubbed before storage."""


async def test_pii_scrubbed_in_notes(mcp_client, seed_task):
    task = await seed_task(name="PII test task")
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Spoke to user@example.com about issue, postcode SW1A 1AA",
    })
    assert not r.is_error, r

    # task_start returns stored content -- verify PII is gone
    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content
    assert len(d["prior_notes"]) == 1
    note_content = d["prior_notes"][0]["content"]
    assert "user@example.com" not in note_content
    assert "SW1A 1AA" not in note_content
    assert "[EMAIL_1]" in note_content
    assert "[POSTCODE_1]" in note_content
