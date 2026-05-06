"""Scenario: save_note always compresses content via compress_text before writing."""
from unittest.mock import MagicMock, patch


async def test_note_content_is_compressed(mcp_client, seed_task):
    task = await seed_task(name="Compression task")
    await mcp_client.call_tool("session_start", {})

    content = "The authentication middleware should check the database connection."
    compressed = "auth middleware→check DB conn."

    mock_compress = MagicMock(return_value=compressed)
    with patch("wizard.tools.task_tools.compress_text", new=mock_compress):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": content,
        })

    assert not r.is_error, r
    assert r.structured_content["note_id"] > 0
    mock_compress.assert_called()


async def test_compressed_content_is_stored(mcp_client, seed_task):
    task = await seed_task(name="Storage task")
    await mcp_client.call_tool("session_start", {})

    content = "The authentication middleware should check the database connection."
    compressed = "auth middleware→check DB conn."

    with patch("wizard.tools.task_tools.compress_text", return_value=compressed):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": content,
        })

    assert not r.is_error, r
