"""Scenario: ctx elicitation across create_task, update_task, save_meeting_summary."""

from unittest.mock import patch

from fastmcp.server.elicitation import AcceptedElicitation


async def test_create_task_elicits_on_duplicate_name(mcp_client, seed_task):
    """When a task with a substring-matching name exists, elicit fires."""
    await seed_task(name="Fix auth bug")

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data=True)

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("create_task", {"name": "Fix auth"})

    assert not r.is_error, r
    assert len(elicit_results) == 1
    assert "Fix auth bug" in elicit_results[0]


async def test_create_task_no_elicit_when_no_duplicate(mcp_client):
    """When no name match exists, elicit is not called."""
    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data=True)

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("create_task", {"name": "Totally new task xyz"})

    assert not r.is_error, r
    assert len(elicit_results) == 0
