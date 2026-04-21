"""Scenario: abandoned session is auto-closed via LLM sampling on next session_start."""

from unittest.mock import MagicMock

import pytest

from wizard.models import NoteType
from wizard.schemas import AutoCloseSummary
from wizard.tools.query_tools import get_session
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_auto_close_via_sampling(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer, session_repo,
):
    task = await seed_task(name="Debug memory leak")

    # Session 1: start, do work, DON'T end
    start1 = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    sid1 = start1.session_id

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Heap dump shows growing object count",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Configure sampling on the new context
    fresh_ctx = type(fake_ctx)()
    sample_result = MagicMock()
    sample_result.result = AutoCloseSummary(
        summary="Investigated memory leak via heap dumps",
        intent="Debug memory leak in service",
        open_loops=["Need to check GC roots"],
    )
    fresh_ctx.sample_result = sample_result

    # Session 2: start -- should auto-close session 1
    start2 = await session_start(
        ctx=fresh_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert start2.session_id != sid1

    # Session 1 should be auto-closed
    assert len(start2.closed_sessions) == 1
    closed = start2.closed_sessions[0]
    assert closed.session_id == sid1
    assert closed.closed_via == "sampling"
    assert closed.note_count >= 1
    assert task.id in closed.task_ids

    # Session 1 state and notes are observable via query tool
    s_detail = await get_session(session_id=sid1, s_repo=session_repo, n_repo=note_repo, db=db_session)
    assert s_detail.session_state is not None
    summary_notes = [n for n in s_detail.notes if n.note_type == NoteType.SESSION_SUMMARY]
    assert len(summary_notes) == 1
