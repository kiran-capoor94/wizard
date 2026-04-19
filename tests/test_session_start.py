"""Tests for session_start behavioral invariants."""

import pytest

import wizard.tools.session_tools as session_tools_mod
from tests.fakes import FakeContext, FakeSessionCloser
from wizard.config import settings
from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus, WizardSession
from wizard.repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
)
from wizard.tools.session_tools import session_start


@pytest.mark.asyncio
async def test_session_start_returns_wizard_context(db_session, monkeypatch):
    """session_start builds wizard_context from settings.knowledge_store."""
    monkeypatch.setattr(settings.knowledge_store, "type", "notion")
    monkeypatch.setattr(settings.knowledge_store.notion, "tasks_db_id", "tasks-abc")
    monkeypatch.setattr(settings.knowledge_store.notion, "daily_parent_id", "daily-xyz")

    result = await session_start(
        ctx=FakeContext(),
        t_repo=TaskRepository(),
        n_repo=NoteRepository(),
        m_repo=MeetingRepository(),
        ts_repo=TaskStateRepository(),
        session_closer=FakeSessionCloser(),
    )

    assert result.wizard_context is not None
    assert result.wizard_context["knowledge_store_type"] == "notion"
    assert result.wizard_context["tasks_db_id"] == "tasks-abc"


@pytest.mark.asyncio
async def test_session_start_wizard_context_null_when_no_ks(db_session, monkeypatch):
    """wizard_context is None when no knowledge store is configured."""
    monkeypatch.setattr(settings.knowledge_store, "type", "")

    result = await session_start(
        ctx=FakeContext(),
        t_repo=TaskRepository(),
        n_repo=NoteRepository(),
        m_repo=MeetingRepository(),
        ts_repo=TaskStateRepository(),
        session_closer=FakeSessionCloser(),
    )

    assert result.wizard_context is None


@pytest.mark.asyncio
async def test_session_start_open_tasks_total_reflects_full_count(db_session):
    """open_tasks_total equals total open tasks; open_tasks is capped at 20."""
    for i in range(25):
        db_session.add(Task(
            name=f"Task {i}",
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.ISSUE,
        ))
    db_session.flush()

    result = await session_start(
        ctx=FakeContext(),
        t_repo=TaskRepository(),
        n_repo=NoteRepository(),
        m_repo=MeetingRepository(),
        ts_repo=TaskStateRepository(),
        session_closer=FakeSessionCloser(),
    )

    assert len(result.open_tasks) == 20
    assert result.open_tasks_total == 25


@pytest.mark.asyncio
async def test_session_start_detects_continuation(db_session, tmp_path, monkeypatch):
    """If current_session_id file exists, continued_from_id is set on the new session."""
    prior_id = 42
    session_id_file = tmp_path / "current_session_id"
    session_id_file.write_text(str(prior_id))
    monkeypatch.setattr(session_tools_mod, "_SESSION_ID_FILE", session_id_file)
    monkeypatch.setattr(
        session_tools_mod, "_AGENT_SESSION_ID_FILE", tmp_path / "pending_agent_session_id"
    )

    result = await session_start(
        ctx=FakeContext(),
        t_repo=TaskRepository(),
        n_repo=NoteRepository(),
        m_repo=MeetingRepository(),
        ts_repo=TaskStateRepository(),
        session_closer=FakeSessionCloser(),
    )

    assert result.continued_from_id == prior_id
    session = db_session.get(WizardSession, result.session_id)
    assert session.continued_from_id == prior_id


@pytest.mark.asyncio
async def test_session_start_reads_and_clears_agent_session_id_file(
    db_session, tmp_path, monkeypatch
):
    """pending_agent_session_id is read, stored on the session, and the file is deleted."""
    agent_uuid = "abc123-agent-uuid"
    agent_file = tmp_path / "pending_agent_session_id"
    agent_file.write_text(agent_uuid)
    monkeypatch.setattr(
        session_tools_mod, "_SESSION_ID_FILE", tmp_path / "current_session_id"
    )
    monkeypatch.setattr(session_tools_mod, "_AGENT_SESSION_ID_FILE", agent_file)

    result = await session_start(
        ctx=FakeContext(),
        t_repo=TaskRepository(),
        n_repo=NoteRepository(),
        m_repo=MeetingRepository(),
        ts_repo=TaskStateRepository(),
        session_closer=FakeSessionCloser(),
    )

    session = db_session.get(WizardSession, result.session_id)
    assert session.agent_session_id == agent_uuid
    assert not agent_file.exists()
