"""Scenario: sampling fails, abandoned session is auto-closed with synthetic summary."""

import pytest

from wizard.models import NoteType, WizardSession
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_auto_close_synthetic_fallback(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = seed_task(name="Fix auth bug")

    # Session 1: start, do work, DON'T end
    start1 = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    sid1 = start1.session_id

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.DECISION,
        content="Switch to JWT tokens",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Session 2: sampling will fail -> synthetic fallback
    fresh_ctx = type(fake_ctx)()
    fresh_ctx.sample_error = RuntimeError("Client does not support sampling")

    start2 = await session_start(
        ctx=fresh_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    assert len(start2.closed_sessions) == 1
    closed = start2.closed_sessions[0]
    assert closed.session_id == sid1
    assert closed.closed_via == "synthetic"
    assert "1 note(s)" in closed.summary
    assert "1 task(s)" in closed.summary

    s1 = db_session.get(WizardSession, sid1)
    assert s1.closed_by == "auto"
    assert s1.summary is not None
