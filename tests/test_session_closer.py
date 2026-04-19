import pytest

from tests.fakes import FakeContext
from wizard.models import WizardSession
from wizard.repositories import NoteRepository
from wizard.security import SecurityService
from wizard.services import SessionCloser


@pytest.mark.asyncio
async def test_session_closer_closes_abandoned_with_synthetic_fallback(db_session):
    abandoned = WizardSession()
    db_session.add(abandoned)
    db_session.flush()
    db_session.refresh(abandoned)

    ctx = FakeContext()
    ctx.sample_error = Exception("sampling unavailable")

    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    results = await closer.close_abandoned(db_session, ctx, current_session_id=999)

    assert len(results) == 1
    assert results[0].session_id == abandoned.id
    assert results[0].closed_via in ("sampling", "synthetic")
    assert abandoned.closed_by == "auto"


@pytest.mark.asyncio
async def test_session_closer_picks_up_hook_closed_sessions(db_session):
    """Sessions with closed_by='hook' must be returned by close_abandoned
    so they enter the synthesis pipeline."""
    hook_session = WizardSession(closed_by="hook", transcript_path="/tmp/t.jsonl")
    db_session.add(hook_session)
    db_session.flush()
    db_session.refresh(hook_session)

    ctx = FakeContext()
    ctx.sample_error = Exception("sampling unavailable")

    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    results = await closer.close_abandoned(db_session, ctx, current_session_id=999)

    result_ids = [r.session_id for r in results]
    assert hook_session.id in result_ids

    # closed_by must NOT be overwritten from 'hook' to 'auto'
    db_session.refresh(hook_session)
    assert hook_session.closed_by == "hook"
