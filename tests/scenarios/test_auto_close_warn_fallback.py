"""Scenario: empty abandoned session, sampling fails, synthetic still works (0 notes)."""

import pytest

from wizard.models import WizardSession
from wizard.tools.session_tools import session_start


@pytest.mark.asyncio
async def test_auto_close_empty_session(
    db_session, fake_ctx, fake_sync, fake_notion, fake_writeback,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    session_closer,
):
    # Session 1: start with NO notes (empty session)
    start1 = await session_start(
        ctx=fake_ctx, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
        closer=session_closer,
    )
    sid1 = start1.session_id

    # Session 2: sampling fails, synthetic has nothing meaningful but still works
    fresh_ctx = type(fake_ctx)()
    fresh_ctx.sample_error = RuntimeError("Sampling unavailable")

    start2 = await session_start(
        ctx=fresh_ctx, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
        closer=session_closer,
    )

    assert len(start2.closed_sessions) == 1
    closed = start2.closed_sessions[0]
    assert closed.session_id == sid1
    assert closed.closed_via == "synthetic"
    assert closed.note_count == 0

    s1 = db_session.get(WizardSession, sid1)
    assert s1.closed_by == "auto"
