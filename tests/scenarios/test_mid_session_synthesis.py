"""Scenario: mid-session background synthesis."""

import asyncio
import contextlib

from wizard.mid_session import MID_SESSION_TASKS


async def test_mid_session_task_registered_when_agent_session_id_provided(mcp_client):
    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
    r = await mcp_client.call_tool("session_start", {"agent_session_id": agent_id})
    assert not r.is_error, r

    task = MID_SESSION_TASKS.get(agent_id)
    assert task is not None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    MID_SESSION_TASKS.pop(agent_id, None)


async def test_mid_session_task_not_registered_without_agent_session_id(mcp_client):
    before = set(MID_SESSION_TASKS.keys())
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert set(MID_SESSION_TASKS.keys()) == before


async def test_mid_session_task_cancelled_on_session_end(mcp_client):
    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001112"
    r = await mcp_client.call_tool("session_start", {"agent_session_id": agent_id})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]
    assert agent_id in MID_SESSION_TASKS

    r = await mcp_client.call_tool("session_end", {
        "session_id": session_id, "summary": "Done", "intent": "Test",
        "working_set": [], "state_delta": "", "open_loops": [],
        "next_actions": [], "closure_status": "clean",
    })
    assert not r.is_error, r
    assert agent_id not in MID_SESSION_TASKS


async def test_auto_close_cancels_mid_session_task(mcp_client, db_session):
    """Auto-closing an abandoned session must clean up its mid-session task."""
    from wizard.models import WizardSession

    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001113"

    # Session 1: start with agent_session_id -- registers a task in MID_SESSION_TASKS
    r = await mcp_client.call_tool("session_start", {"agent_session_id": agent_id})
    assert not r.is_error, r
    start1_session_id = r.structured_content["session_id"]
    assert agent_id in MID_SESSION_TASKS

    # Session 2: new start without ending session 1 -- triggers auto-close of session 1
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert r.structured_content["session_id"] is not None

    # Mid-session task for the abandoned session must have been cleaned up
    assert agent_id not in MID_SESSION_TASKS

    # The abandoned session must have been auto-closed
    session1 = db_session.get(WizardSession, start1_session_id)
    assert session1 is not None
    db_session.refresh(session1)
    assert session1.closed_by == "auto"


async def test_session_start_sets_agent_claude_code(mcp_client, db_session):
    """session_start must set session.agent = 'claude-code' for mid-session synthesis."""
    from wizard.models import WizardSession

    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001114"
    r = await mcp_client.call_tool("session_start", {"agent_session_id": agent_id})
    assert not r.is_error, r

    session = db_session.get(WizardSession, r.structured_content["session_id"])
    assert session is not None
    assert session.agent == "claude-code"

    # Cleanup the background task
    task = MID_SESSION_TASKS.pop(agent_id, None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_session_start_without_agent_session_id_leaves_agent_none(mcp_client, db_session):
    """session_start without agent_session_id must not stamp agent='claude-code'."""
    from wizard.models import WizardSession

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session = db_session.get(WizardSession, r.structured_content["session_id"])
    assert session is not None
    assert session.agent is None
