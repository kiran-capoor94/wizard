"""Scenario: ctx elicitation across create_task, update_task, save_meeting_summary, save_note."""

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


async def test_update_task_elicits_on_done(mcp_client, seed_task):
    """When marking a task done, elicit fires for confirmation."""
    task = await seed_task(name="Deploy feature xyz")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data=True)

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": "done"})

    assert not r.is_error, r
    assert len(elicit_results) == 1
    assert "done" in elicit_results[0].lower()


async def test_update_task_cancellation_aborts_done(mcp_client, seed_task):
    """Cancelling the done-confirmation elicitation leaves the task status unchanged."""
    task = await seed_task(name="Deploy feature to cancel")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    class CancelledElicitation:
        pass

    async def fake_elicit_cancel(self, message, **kwargs):
        return CancelledElicitation()

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit_cancel):
        r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": "done"})

    assert not r.is_error, r
    result = r.structured_content
    assert result["updated_fields"] == [], f"Expected no fields updated, got {result['updated_fields']}"


async def test_update_task_no_elicit_on_other_status(mcp_client, seed_task):
    """Non-done status changes do not trigger elicitation."""
    task = await seed_task(name="Deploy feature abc")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data=True)

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("update_task", {"task_id": task.id, "status": "in_progress"})

    assert not r.is_error, r
    assert len(elicit_results) == 0


async def test_save_meeting_summary_elicits_on_task_links(mcp_client, seed_task):
    """save_meeting_summary elicits when task_ids are provided."""
    task = await seed_task(name="Follow up on meeting")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    r = await mcp_client.call_tool("ingest_meeting", {
        "title": "Sprint planning",
        "content": "We discussed priorities.",
    })
    assert not r.is_error, r
    meeting_id = r.structured_content["meeting_id"]

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data=True)

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("save_meeting_summary", {
            "meeting_id": meeting_id,
            "summary": "We decided to focus on auth.",
            "task_ids": [task.id],
        })

    assert not r.is_error, r
    assert len(elicit_results) == 1


async def test_save_meeting_summary_no_elicit_without_task_ids(mcp_client):
    """save_meeting_summary does not elicit when no task_ids provided."""
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    r = await mcp_client.call_tool("ingest_meeting", {
        "title": "Standup",
        "content": "Quick sync.",
    })
    assert not r.is_error, r
    meeting_id = r.structured_content["meeting_id"]

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data=True)

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("save_meeting_summary", {
            "meeting_id": meeting_id,
            "summary": "Nothing to note.",
        })

    assert not r.is_error, r
    assert len(elicit_results) == 0


async def test_save_note_no_elicit_for_investigation_without_mental_model(mcp_client, seed_task):
    """save_note does not elicit when note_type is investigation and no mental_model provided."""
    task = await seed_task(name="Investigate caching issue")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data="Redis TTL mismatch causes stale reads.")

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "investigation",
            "content": "Cache entries expire before the TTL we expect.",
        })

    assert not r.is_error, r
    assert len(elicit_results) == 0


async def test_save_note_no_elicit_when_mental_model_provided(mcp_client, seed_task):
    """save_note does not elicit when mental_model is already supplied."""
    task = await seed_task(name="Investigate DB latency")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data="Some model.")

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "investigation",
            "content": "Slow queries in production.",
            "mental_model": "Unindexed FK column causes full table scans.",
        })

    assert not r.is_error, r
    assert len(elicit_results) == 0


async def test_save_note_no_elicit_for_decision_without_mental_model(mcp_client, seed_task):
    """save_note does not elicit when note_type is decision and no mental_model provided."""
    task = await seed_task(name="Decide on caching strategy")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data="We will use Redis with a 5-minute TTL.")

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "decision",
            "content": "Chose Redis over Memcached for its persistence support.",
        })

    assert not r.is_error, r
    assert len(elicit_results) == 0
    assert r.structured_content["mental_model_saved"] is False


async def test_save_meeting_summary_cancellation_skips_task_links(mcp_client, seed_task):
    """Cancelling the task-link elicitation leaves tasks unlinked."""
    task = await seed_task(name="Task to maybe link")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    r = await mcp_client.call_tool("ingest_meeting", {
        "title": "Planning meeting",
        "content": "We discussed next steps.",
    })
    assert not r.is_error, r
    meeting_id = r.structured_content["meeting_id"]

    class CancelledElicitation:
        pass

    async def fake_elicit_cancel(self, message, **kwargs):
        return CancelledElicitation()

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit_cancel):
        r = await mcp_client.call_tool("save_meeting_summary", {
            "meeting_id": meeting_id,
            "summary": "We decided to focus on performance.",
            "task_ids": [task.id],
        })

    assert not r.is_error, r
    assert r.structured_content["tasks_linked"] == 0


async def test_save_note_no_elicit_for_docs_type(mcp_client, seed_task):
    """save_note does not elicit for note types other than investigation/decision."""
    task = await seed_task(name="Document API endpoints")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r

    elicit_results = []

    async def fake_elicit(self, message, **kwargs):
        elicit_results.append(message)
        return AcceptedElicitation(data="Some model.")

    with patch("fastmcp.server.context.Context.elicit", new=fake_elicit):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id,
            "note_type": "docs",
            "content": "API uses REST with JSON payloads.",
        })

    assert not r.is_error, r
    assert len(elicit_results) == 0
