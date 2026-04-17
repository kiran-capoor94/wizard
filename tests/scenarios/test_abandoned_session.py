"""Scenario: session started, work done, session_end never called. New session starts."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note, task_start


@pytest.mark.asyncio
async def test_abandoned_session(
    db_session, fake_ctx, fake_sync, fake_notion, fake_writeback,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task,
):
    task = seed_task(name="Debug memory leak")

    # Session 1: start, do work, DON'T end
    start_resp = await session_start(
        ctx=fake_ctx, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
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
    start_resp2 = await session_start(
        ctx=fresh_ctx, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
    )
    assert start_resp2.session_id is not None
    assert start_resp2.session_id != session_1_id

    # Notes from session 1 are still there
    ts_resp = await task_start(
        ctx=fresh_ctx, task_id=task.id,
        t_repo=task_repo, n_repo=note_repo,
    )
    assert ts_resp.compounding is True
    assert sum(ts_resp.notes_by_type.values()) >= 1
