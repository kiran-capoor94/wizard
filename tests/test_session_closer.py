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
