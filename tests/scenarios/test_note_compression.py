"""Scenario: save_note compresses content > 1000 chars before writing."""
from unittest.mock import AsyncMock, patch


async def test_long_note_is_compressed(mcp_client, seed_task):
    task = await seed_task(name="Compression task")
    await mcp_client.call_tool("session_start", {})

    long_content = "x" * 1001
    compressed = "Compressed: found issue in auth.py:42 — token expiry not checked."

    mock_compress = AsyncMock(return_value=compressed)
    with patch(
        "wizard.tools.task_tools._compress_note_content",
        new=mock_compress,
    ):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "investigation",
            "content": long_content,
        })

    assert not r.is_error, r
    assert r.structured_content["note_id"] > 0
    mock_compress.assert_called_once()


async def test_short_note_skips_compression(mcp_client, seed_task):
    task = await seed_task(name="No compression task")
    await mcp_client.call_tool("session_start", {})

    short_content = "Token expiry bug at auth.py:42."

    with patch(
        "wizard.tools.task_tools._compress_note_content",
        new=AsyncMock(side_effect=AssertionError("should not compress")),
    ):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "investigation",
            "content": short_content,
        })

    assert not r.is_error, r
