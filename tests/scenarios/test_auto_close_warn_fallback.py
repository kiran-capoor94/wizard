"""Scenario: empty abandoned session, sampling fails, synthetic still works (0 notes)."""

import pytest

from wizard.models import WizardSession
from wizard.tools.session_tools import session_start


@pytest.mark.asyncio
async def test_auto_close_empty_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    session_closer, capture_synthesiser,
):
    # Session 1: start with NO notes (empty session)
    start1 = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
        capture_synthesiser=capture_synthesiser,
    )
    sid1 = start1.session_id

    # Session 2: sampling fails, synthetic has nothing meaningful but still works
    fresh_ctx = type(fake_ctx)()
    fresh_ctx.sample_error = RuntimeError("Sampling unavailable")

    start2 = await session_start(
        ctx=fresh_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
        capture_synthesiser=capture_synthesiser,
    )

    assert len(start2.closed_sessions) == 1
    closed = start2.closed_sessions[0]
    assert closed.session_id == sid1
    assert closed.closed_via == "synthetic"
    assert closed.note_count == 0

    s1 = db_session.get(WizardSession, sid1)
    assert s1.closed_by == "auto"
