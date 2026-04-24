"""Scenario: abandoned session is auto-closed; when sampling succeeds, closed_via='sampling'."""

from unittest.mock import patch


async def test_auto_close_via_sampling(mcp_client, seed_task):
    task = await seed_task(name="Debug memory leak")

    # Session 1: start, save a note, DON'T end
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    sid1 = r.structured_content["session_id"]

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Heap dump shows growing object count",
    })
    assert not r.is_error, r

    # Patch _try_sampling to simulate a successful LLM sampling response
    async def _fake_sampling(_self, _ctx, _notes):
        return ("Investigated memory leak via heap dumps", "sampling")

    with patch("wizard.services.SessionCloser._try_sampling", _fake_sampling):
        r = await mcp_client.call_tool("session_start", {})

    assert not r.is_error, r
    assert r.structured_content["session_id"] != sid1

    closed = r.structured_content["closed_sessions"]
    assert len(closed) == 1
    assert closed[0]["session_id"] == sid1
    assert closed[0]["closed_via"] == "sampling"
    assert closed[0]["note_count"] >= 1
    assert task.id in closed[0]["task_ids"]
