"""Scenario: abandoned session is auto-closed via LLM sampling on next session_start."""

from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from wizard.models import Note, NoteType, WizardSession
from wizard.schemas import AutoCloseSummary
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_auto_close_via_sampling(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = seed_task(name="Debug memory leak")

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
        n_repo=note_repo,
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

    # DB state: session 1 has summary and closed_by
    s1 = db_session.get(WizardSession, sid1)
    assert s1.summary is not None
    assert s1.closed_by == "auto"
    assert s1.session_state is not None

    # A session_summary note was created for session 1
    summary_notes = db_session.exec(
        select(Note).where(
            Note.session_id == sid1,
            Note.note_type == NoteType.SESSION_SUMMARY,
        )
    ).all()
    assert len(summary_notes) == 1
