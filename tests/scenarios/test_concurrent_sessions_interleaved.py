"""Scenario: two sessions opened, notes saved under session B, resume session A."""

import pytest

from wizard.models import NoteType
from wizard.tools.query_tools import get_session
from wizard.tools.session_tools import session_end, session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_concurrent_sessions(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer, session_repo,
):
    task = await seed_task(name="Shared task")

    # Session A
    ctx_a = type(fake_ctx)()
    start_a = await session_start(
        ctx=ctx_a,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session_a_id = start_a.session_id

    # Session B (without ending A)
    ctx_b = type(fake_ctx)()
    start_b = await session_start(
        ctx=ctx_b,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session_b_id = start_b.session_id
    assert session_b_id != session_a_id

    # Save note under session B
    note_resp = await save_note(
        ctx=ctx_b, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Note from session B",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Note appears in session B's note list
    s_b_detail = await get_session(session_id=session_b_id, s_repo=session_repo, n_repo=note_repo, db=db_session)
    assert any(n.id == note_resp.note_id for n in s_b_detail.notes)

    # End session B
    await session_end(
        ctx=ctx_b, session_id=session_b_id,
        summary="Session B work", intent="test",
        working_set=[task.id], state_delta="B done",
        open_loops=[], next_actions=[],
        closure_status="clean",
        sec=security, n_repo=note_repo,
    )

    # End session A (was never used, but ending it should work)
    await session_end(
        ctx=ctx_a, session_id=session_a_id,
        summary="Session A (no work)", intent="test",
        working_set=[], state_delta="nothing",
        open_loops=[], next_actions=[],
        closure_status="clean",
        sec=security, n_repo=note_repo,
    )
