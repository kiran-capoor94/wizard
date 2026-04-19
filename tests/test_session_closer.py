import datetime

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
    results = await closer.close_recent_abandoned(db_session, ctx, current_session_id=999)

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
    results = await closer.close_recent_abandoned(db_session, ctx, current_session_id=999)

    result_ids = [r.session_id for r in results]
    assert hook_session.id in result_ids

    # closed_by must NOT be overwritten from 'hook' to 'auto'
    db_session.refresh(hook_session)
    assert hook_session.closed_by == "hook"


@pytest.mark.asyncio
async def test_find_recent_abandoned_returns_only_recent(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    from wizard.services import SessionCloser

    recent = WizardSession()
    recent.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    db_session.add(recent)

    old = WizardSession()
    old.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=48)
    db_session.add(old)

    db_session.flush()
    db_session.refresh(recent)
    db_session.refresh(old)

    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    found = closer._find_recent_abandoned(db_session, current_session_id=999)
    found_ids = [s.id for s in found]

    assert recent.id in found_ids
    assert old.id not in found_ids


@pytest.mark.asyncio
async def test_find_old_abandoned_returns_only_old(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    from wizard.services import SessionCloser

    recent = WizardSession()
    recent.created_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
    db_session.add(recent)

    old = WizardSession()
    old.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=48)
    db_session.add(old)

    db_session.flush()
    db_session.refresh(recent)
    db_session.refresh(old)

    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    found = closer._find_old_abandoned(db_session, current_session_id=999)
    found_ids = [s.id for s in found]

    assert old.id in found_ids
    assert recent.id not in found_ids


@pytest.mark.asyncio
async def test_close_recent_abandoned_ignores_old_sessions(db_session):
    from tests.fakes import FakeContext
    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    from wizard.services import SessionCloser

    old = WizardSession()
    old.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=48)
    db_session.add(old)
    db_session.flush()
    db_session.refresh(old)

    ctx = FakeContext()
    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    results = await closer.close_recent_abandoned(db_session, ctx, current_session_id=999)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_close_abandoned_background_processes_old_sessions(db_engine):
    """close_abandoned_background opens its own session and closes old sessions."""
    from contextlib import contextmanager
    from unittest.mock import patch

    from sqlmodel import Session as SQLSession

    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    from wizard.services import SessionCloser

    with SQLSession(db_engine) as db:
        session = WizardSession()
        session.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=48)
        db.add(session)
        db.commit()
        db.refresh(session)
        old_id = session.id

    @contextmanager
    def fake_get_session():
        with SQLSession(db_engine) as s:
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise

    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    with patch("wizard.services.get_session", fake_get_session):
        await closer.close_abandoned_background(current_session_id=999)

    with SQLSession(db_engine) as db:
        closed = db.get(WizardSession, old_id)
        assert closed is not None
        assert closed.summary is not None


@pytest.mark.asyncio
async def test_close_one_without_ctx_uses_synthetic(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    from wizard.services import SessionCloser

    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    closer = SessionCloser(note_repo=NoteRepository(), security=SecurityService())
    result = await closer._close_one(db_session, session, ctx=None)

    assert result.closed_via == "synthetic"
    assert result.session_id == session.id
