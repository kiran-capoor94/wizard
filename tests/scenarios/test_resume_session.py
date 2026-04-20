"""Scenario: start, work, end, then resume from a new session."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import resume_session, session_end, session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_resume_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = await seed_task(name="Investigate auth issue")

    # Session 1: start, save note, end
    start_resp = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session_1_id = start_resp.session_id

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Found a suspicious pattern in the logs",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    await session_end(
        ctx=fake_ctx, session_id=session_1_id,
        summary="Investigated auth, found log pattern",
        intent="Investigation", working_set=[task.id],
        state_delta="Found suspicious log pattern",
        open_loops=["Need to check prod logs"],
        next_actions=["Compare with staging"],
        closure_status="interrupted",
        sec=security, n_repo=note_repo,
    )

    # Session 2: resume from session 1
    fresh_ctx = type(fake_ctx)()
    resume_resp = await resume_session(
        ctx=fresh_ctx, session_id=session_1_id,
        t_repo=task_repo, n_repo=note_repo, m_repo=meeting_repo,
    )
    assert resume_resp.resumed_from_session_id == session_1_id
    assert resume_resp.session_id != session_1_id
    assert resume_resp.continued_from_id == session_1_id
    assert resume_resp.session_state is not None
    assert resume_resp.session_state.closure_status == "interrupted"
    assert len(resume_resp.session_state.open_loops) == 1
    assert len(resume_resp.prior_notes) > 0
