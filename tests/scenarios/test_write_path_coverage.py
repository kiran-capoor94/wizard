"""End-to-end write-path PII pseudonymisation coverage.

Verifies that person names written through MCP tools are pseudonymised
before reaching SQLite, and that the pseudonymised form is what is stored.
"""

from unittest.mock import patch

import pytest

from wizard.database import get_session
from wizard.models import Note, NoteType, WizardSession
from wizard.repositories import NoteRepository
from wizard.security import PseudonymStore, SecurityService


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
