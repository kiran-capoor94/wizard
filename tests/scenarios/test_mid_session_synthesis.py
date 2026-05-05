"""Scenario: mid-session background synthesis."""

from wizard.mid_session import MID_SESSION_TASKS


async def test_mid_session_task_not_registered_without_agent_session_id(mcp_client):
    before = set(MID_SESSION_TASKS.keys())
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert set(MID_SESSION_TASKS.keys()) == before


async def test_session_start_sets_agent_claude_code(mcp_client, db_session):
    """session_start must set session.agent = 'claude-code' for mid-session synthesis."""
    from wizard.models import WizardSession

    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001114"
    r = await mcp_client.call_tool("session_start", {"agent_session_id": agent_id})
    assert not r.is_error, r

    session = db_session.get(WizardSession, r.structured_content["session_id"])
    assert session is not None
    assert session.agent == "claude-code"

    MID_SESSION_TASKS.pop(agent_id, None)


async def test_session_start_without_agent_session_id_leaves_agent_none(mcp_client, db_session):
    """session_start without agent_session_id must not stamp agent='claude-code'."""
    from wizard.models import WizardSession

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session = db_session.get(WizardSession, r.structured_content["session_id"])
    assert session is not None
    assert session.agent is None
