"""Scenario: session started, work done, session_end never called. New session starts."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note, task_start


@pytest.mark.asyncio
async def test_abandoned_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = await seed_task(name="Debug memory leak")

    # Session 1: start, do work, DON'T end
    start_resp = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session_1_id = start_resp.session_id

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Heap dump shows growing object count",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Session 2: start fresh without ending session 1
    fresh_ctx = type(fake_ctx)()
    fresh_ctx.sample_error = RuntimeError("No sampling in tests")
    start_resp2 = await session_start(
        ctx=fresh_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert start_resp2.session_id is not None
    assert start_resp2.session_id != session_1_id

    # Session 1 was auto-closed — observable via the response
    assert len(start_resp2.closed_sessions) == 1
    assert start_resp2.closed_sessions[0].session_id == session_1_id
    assert start_resp2.closed_sessions[0].closed_via == "synthetic"
    assert start_resp2.closed_sessions[0].summary is not None

    # Notes from session 1 are still there
    ts_resp = await task_start(
        ctx=fresh_ctx, task_id=task.id,
        t_repo=task_repo, n_repo=note_repo,
    )
    assert ts_resp.compounding is True
    assert sum(ts_resp.notes_by_type.values()) >= 1
