import pytest

from tests.fakes import FakeContext, FakeSessionCloser
from wizard.repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
)
from wizard.schemas import SessionStartResponse
from wizard.security import SecurityService
from wizard.tools.session_tools import session_start
from wizard.transcript import CaptureSynthesiser, TranscriptReader


@pytest.mark.asyncio
async def test_session_start_returns_wizard_context(db_session, monkeypatch):
    """session_start builds wizard_context from settings.knowledge_store."""
    from wizard.config import settings
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
        capture_synthesiser=CaptureSynthesiser(
            reader=TranscriptReader(), note_repo=NoteRepository(), security=SecurityService(),
        ),
    )

    assert result.wizard_context is not None
    assert result.wizard_context["knowledge_store_type"] == "notion"
    assert result.wizard_context["tasks_db_id"] == "tasks-abc"


@pytest.mark.asyncio
async def test_session_start_wizard_context_null_when_no_ks(db_session, monkeypatch):
    from wizard.config import settings
    monkeypatch.setattr(settings.knowledge_store, "type", "")

    result = await session_start(
        ctx=FakeContext(),
        t_repo=TaskRepository(),
        n_repo=NoteRepository(),
        m_repo=MeetingRepository(),
        ts_repo=TaskStateRepository(),
        session_closer=FakeSessionCloser(),
        capture_synthesiser=CaptureSynthesiser(
            reader=TranscriptReader(), note_repo=NoteRepository(), security=SecurityService(),
        ),
    )

    assert result.wizard_context is None


@pytest.mark.asyncio
async def test_session_start_has_no_sync_results(db_session):
    assert "sync_results" not in SessionStartResponse.model_fields
    assert "daily_page" not in SessionStartResponse.model_fields
