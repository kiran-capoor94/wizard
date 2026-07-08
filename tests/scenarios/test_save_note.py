"""Scenario: save_note stores content verbatim (PII-scrubbed only, never rewritten)."""


async def test_note_content_is_stored_verbatim(mcp_client, seed_task):
    task = await seed_task(name="Verbatim storage task")
    await mcp_client.call_tool("session_start", {})

    content = "The authentication middleware should check the database connection."

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": content,
    })
    assert not r.is_error, r

    rewind = await mcp_client.call_tool("rewind_task", {"task_id": task.id})
    assert not rewind.is_error, rewind
    previews = [n["preview"] for n in rewind.structured_content["timeline"]]
    assert content in previews


async def test_note_content_with_technical_tokens_survives_unmodified(mcp_client, seed_task):
    """Regression test for the corruption bug this fix addresses: version strings,
    file paths, and other punctuation-adjacent tokens must never be altered."""
    task = await seed_task(name="Technical token task")
    await mcp_client.call_tool("session_start", {})

    content = (
        "Upgraded installed tool from v2.2.38 to v2.2.40. "
        "Clean up [TEST] task/meeting created during this smoke test."
    )

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": content,
    })
    assert not r.is_error, r

    rewind = await mcp_client.call_tool("rewind_task", {"task_id": task.id})
    previews = [n["preview"] for n in rewind.structured_content["timeline"]]
    assert content in previews


async def test_mental_model_truncated_at_max_chars(mcp_client, seed_task):
    from wizard.models import MENTAL_MODEL_MAX_CHARS

    task = await seed_task(name="Mental model cap task")
    await mcp_client.call_tool("session_start", {})

    long_mental_model = "x" * (MENTAL_MODEL_MAX_CHARS + 500)

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "Some investigation content.",
        "mental_model": long_mental_model,
    })
    assert not r.is_error, r

    rewind = await mcp_client.call_tool("rewind_task", {"task_id": task.id})
    stored_mental_model = rewind.structured_content["timeline"][0]["mental_model"]
    assert len(stored_mental_model) == MENTAL_MODEL_MAX_CHARS
