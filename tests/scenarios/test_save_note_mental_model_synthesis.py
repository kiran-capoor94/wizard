"""Scenario: save_note auto-synthesises mental_model via ctx.sample when agent omits it."""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_mental_model_synthesised_on_second_note(mcp_client, seed_task):
    """On 2nd note with no mental_model and ctx.sample available, one is synthesised."""
    task = await seed_task(name="synth mm task")
    await mcp_client.call_tool("session_start", {})

    r1 = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "Traced the auth middleware. Token expiry check missing.",
    })
    assert not r1.is_error, r1
    assert not r1.structured_content["mental_model_saved"]

    with patch(
        "wizard.tools.task_tools.sample_mental_model",
        new=AsyncMock(return_value="Auth middleware lacks expiry. Fix: add check in verify()."),
    ):
        r2 = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": "Confirmed: jwt.verify() never called on refresh path.",
        })
    assert not r2.is_error, r2
    assert r2.structured_content["mental_model_saved"]


@pytest.mark.asyncio
async def test_mental_model_not_synthesised_when_already_exists(mcp_client, seed_task):
    """ctx.sample is NOT called when a mental model already exists for the task."""
    task = await seed_task(name="existing mm task")
    await mcp_client.call_tool("session_start", {})

    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "First note.",
        "mental_model": "Already have a model.",
    })

    with patch(
        "wizard.tools.task_tools.sample_mental_model",
        new=AsyncMock(return_value="should not appear"),
    ) as mock_sample:
        r2 = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": "Second note — model already present.",
        })
    mock_sample.assert_not_called()
    assert not r2.is_error, r2


@pytest.mark.asyncio
async def test_mental_model_synthesis_silent_on_failure(mcp_client, seed_task):
    """If sample_mental_model raises, save_note still succeeds."""
    task = await seed_task(name="synth failure task")
    await mcp_client.call_tool("session_start", {})

    await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "INVESTIGATION", "content": "First note.",
    })

    with patch(
        "wizard.tools.task_tools.sample_mental_model",
        new=AsyncMock(side_effect=RuntimeError("transport broken")),
    ):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "INVESTIGATION",
            "content": "Second note — synthesis will fail.",
        })
    assert not r.is_error, r
    assert not r.structured_content["mental_model_saved"]
