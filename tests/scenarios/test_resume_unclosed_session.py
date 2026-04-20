"""Scenario: resume a session that was never cleanly ended."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import resume_session, session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_resume_unclosed_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = await seed_task(name="Unclosed session task")

    # Start session, do work, DON'T end
    start_resp = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session_id = start_resp.session_id

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Partial work before crash",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Resume the unclosed session directly
    fresh_ctx = type(fake_ctx)()
    resume_resp = await resume_session(
        ctx=fresh_ctx, session_id=session_id,
        t_repo=task_repo, n_repo=note_repo, m_repo=meeting_repo,
    )

    # session_state is None because session_end was never called
    assert resume_resp.session_state is None
    assert resume_resp.resumed_from_session_id == session_id
    assert resume_resp.continued_from_id == session_id
    # But prior notes are still returned
    assert len(resume_resp.prior_notes) > 0
