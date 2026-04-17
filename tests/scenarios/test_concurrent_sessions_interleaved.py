"""Scenario: two sessions opened, notes saved under session B, resume session A."""

import pytest

from wizard.models import Note, NoteType
from wizard.tools.session_tools import session_end, session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_concurrent_sessions(
    db_session, fake_ctx, fake_sync, fake_notion, fake_writeback,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task,
):
    task = seed_task(name="Shared task")

    # Session A
    ctx_a = type(fake_ctx)()
    start_a = await session_start(
        ctx=ctx_a, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
    )
    session_a_id = start_a.session_id

    # Session B (without ending A)
    ctx_b = type(fake_ctx)()
    start_b = await session_start(
        ctx=ctx_b, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
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

    # Verify note is attached to session B
    note = db_session.get(Note, note_resp.note_id)
    assert note is not None
    assert note.session_id == session_b_id

    # End session B
    await session_end(
        ctx=ctx_b, session_id=session_b_id,
        summary="Session B work", intent="test",
        working_set=[task.id], state_delta="B done",
        open_loops=[], next_actions=[],
        closure_status="clean",
        sec=security, n_repo=note_repo, wb=fake_writeback,
    )

    # End session A (was never used, but ending it should work)
    await session_end(
        ctx=ctx_a, session_id=session_a_id,
        summary="Session A (no work)", intent="test",
        working_set=[], state_delta="nothing",
        open_loops=[], next_actions=[],
        closure_status="clean",
        sec=security, n_repo=note_repo, wb=fake_writeback,
    )
