"""End-to-end write-path PII pseudonymisation coverage.

Verifies that person names written through MCP tools are pseudonymised
before reaching SQLite, and that the pseudonymised form is what is stored.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlmodel import create_engine

from wizard.security import PseudonymStore, SecurityService


@pytest.fixture
def pii_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE pseudonym_map ("
            "id INTEGER PRIMARY KEY, "
            "original_hash TEXT NOT NULL UNIQUE, "
            "entity_type TEXT NOT NULL, "
            "fake_value TEXT NOT NULL, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.commit()
    return engine


@pytest.fixture
def security_with_store(pii_engine):
    return SecurityService(
        allowlist=[r"ENG-\d+"],
        enabled=True,
        store=PseudonymStore(engine=pii_engine),
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
            {"name": "Task A for John Smith", "priority": "medium", "category": "issue"},
        )
        r2 = await mcp_client.call_tool(
            "create_task",
            {"name": "Task B for John Smith", "priority": "low", "category": "issue"},
        )

    t1 = (await mcp_client.call_tool("get_task", {"task_id": r1.structured_content["task_id"]})).structured_content["task"]["name"]
    t2 = (await mcp_client.call_tool("get_task", {"task_id": r2.structured_content["task_id"]})).structured_content["task"]["name"]

    fake_in_t1 = t1.replace("Task A for ", "")
    fake_in_t2 = t2.replace("Task B for ", "")
    assert fake_in_t1 == fake_in_t2


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
