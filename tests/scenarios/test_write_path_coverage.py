"""End-to-end write-path PII pseudonymisation coverage.

Verifies that person names written through MCP tools are pseudonymised
before reaching SQLite, and that the pseudonymised form is what is stored.
"""

from unittest.mock import patch

import pytest
from sqlmodel import select

from wizard.database import get_session
from wizard.models import Note, NoteType, ToolCall, WizardSession
from wizard.repositories import NoteRepository
from wizard.security import PseudonymStore, SecurityService
from wizard.tool_call_buffer import ToolCallBuffer


@pytest.fixture
def security_with_store(pseudonym_engine):
    return SecurityService(
        allowlist=[r"ENG-\d+"],
        enabled=True,
        store=PseudonymStore(engine=pseudonym_engine),
    )


@pytest.mark.asyncio
async def test_create_task_pseudonymises_person_name(mcp_client, security_with_store):
    with patch("wizard.deps.get_security", return_value=security_with_store):
        result = await mcp_client.call_tool(
            "create_task",
            {
                "name": "Follow up with Dr Sarah Ahmed re: results",
                "priority": "medium",
                "category": "issue",
            },
        )
    assert not result.is_error
    task_id = result.structured_content["task_id"]

    read_result = await mcp_client.call_tool("get_task", {"task_id": task_id})
    assert not read_result.is_error
    stored_name = read_result.structured_content["task"]["name"]
    assert "Sarah Ahmed" not in stored_name


@pytest.mark.asyncio
async def test_save_note_pseudonymises_person_name(mcp_client, security_with_store):
    session_result = await mcp_client.call_tool("session_start", {})
    assert not session_result.is_error

    task_result = await mcp_client.call_tool(
        "create_task",
        {"name": "Test task", "priority": "medium", "category": "issue"},
    )
    task_id = task_result.structured_content["task_id"]

    with patch("wizard.deps.get_security", return_value=security_with_store):
        note_result = await mcp_client.call_tool(
            "save_note",
            {
                "task_id": task_id,
                "note_type": "investigation",
                "content": "Spoke with John Smith about the issue.",
            },
        )
    assert not note_result.is_error

    read_result = await mcp_client.call_tool("get_task", {"task_id": task_id})
    notes = read_result.structured_content["notes"]
    assert notes
    assert "John Smith" not in notes[0]["content"]


@pytest.mark.asyncio
async def test_same_name_consistent_across_tasks(mcp_client, security_with_store):
    with patch("wizard.deps.get_security", return_value=security_with_store):
        r1 = await mcp_client.call_tool(
            "create_task",
            {"name": "Meeting with Dr John Smith about Task A", "priority": "medium", "category": "issue"},
        )
        r2 = await mcp_client.call_tool(
            "create_task",
            {"name": "Meeting with Dr John Smith about Task B", "priority": "low", "category": "issue"},
        )

    t1 = (await mcp_client.call_tool("get_task", {"task_id": r1.structured_content["task_id"]})).structured_content["task"]["name"]
    t2 = (await mcp_client.call_tool("get_task", {"task_id": r2.structured_content["task_id"]})).structured_content["task"]["name"]

    assert "John Smith" not in t1
    assert "John Smith" not in t2
    # Both tasks should use the same pseudonym for Dr John Smith
    assert t1.replace("about Task A", "") == t2.replace("about Task B", "")


@pytest.mark.asyncio
async def test_jira_upsert_path_pseudonymises_name(mcp_client, security_with_store):
    with patch("wizard.deps.get_security", return_value=security_with_store):
        result = await mcp_client.call_tool(
            "create_task",
            {
                "name": "Referral from Dr James Wong",
                "priority": "high",
                "category": "issue",
                "source_id": "JIRA-999",
                "source_type": "jira",
            },
        )
    assert not result.is_error
    task_id = result.structured_content["task_id"]

    read_result = await mcp_client.call_tool("get_task", {"task_id": task_id})
    stored_name = read_result.structured_content["task"]["name"]
    assert "James Wong" not in stored_name


@pytest.mark.asyncio
async def test_save_all_inserts_multiple_notes_in_one_flush(mcp_client, seed_task):
    """save_all must persist N notes and return them all with assigned IDs."""
    task = await seed_task(name="Batch insert task")

    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)

        notes = [
            Note(
                note_type=NoteType.INVESTIGATION,
                content=f"Note {i}",
                task_id=task.id,
                session_id=session.id,
            )
            for i in range(5)
        ]
        repo = NoteRepository()
        saved = repo.save_all(db, notes)
        assert len(saved) == 5
        assert all(n.id is not None for n in saved)


@pytest.mark.asyncio
async def test_tool_call_buffer_flushes_on_demand():
    """ToolCallBuffer.flush_now must persist enqueued items and clear the queue."""
    buffer = ToolCallBuffer()

    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        session_id = session.id

        buffer.enqueue(tool_name="save_note", session_id=session_id)
        buffer.enqueue(tool_name="task_start", session_id=session_id)

        await buffer.flush_now(db)
        rows = db.exec(select(ToolCall).where(ToolCall.session_id == session_id)).all()
        tool_names = {r.tool_name for r in rows}

    assert len(rows) == 2
    assert tool_names == {"save_note", "task_start"}


@pytest.mark.asyncio
async def test_session_state_only_written_on_allowlisted_tools(mcp_client, seed_task):
    """SessionState snapshot must only be written on task_start and session_end, not on save_note."""
    task = await seed_task(name="Lazy snapshot task")

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]

    with get_session() as db:
        before = db.get(WizardSession, session_id)
        state_before = before.session_state if before else None

    await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "investigation",
        "content": "some finding",
    })

    with get_session() as db:
        after = db.get(WizardSession, session_id)
        state_after = after.session_state if after else None

    assert state_before == state_after, (
        "SessionState was written by save_note — should only write on task_start/session_end"
    )


@pytest.mark.asyncio
async def test_session_end_prunes_old_tool_calls(mcp_client, db_session):
    """session_end must delete ToolCall rows older than 90 days."""
    import datetime as dt_module

    stale_date = dt_module.datetime.utcnow() - dt_module.timedelta(days=91)
    old_call = ToolCall(tool_name="old_tool", session_id=None)
    old_call.called_at = stale_date
    db_session.add(old_call)
    db_session.flush()
    old_id = old_call.id

    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    session_id = r.structured_content["session_id"]

    r = await mcp_client.call_tool("session_end", {
        "session_id": session_id,
        "summary": "test session",
        "intent": "testing",
        "working_set": [],
        "state_delta": "",
        "open_loops": [],
        "next_actions": [],
        "closure_status": "clean",
    })
    assert not r.is_error, r

    db_session.expire_all()
    gone = db_session.get(ToolCall, old_id)
    assert gone is None, "ToolCall row older than 90 days was not pruned by session_end"
