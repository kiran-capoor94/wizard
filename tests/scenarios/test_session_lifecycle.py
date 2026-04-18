"""Scenario: full session lifecycle -- start, task_start, save_note, end."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import session_end, session_start
from wizard.tools.task_tools import save_note, task_start, what_am_i_missing


@pytest.mark.asyncio
async def test_session_lifecycle(
    db_session, fake_ctx, fake_sync, fake_notion, fake_writeback,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    # Pre-seed a task so session_start has something to show
    task = seed_task(name="Fix auth bug", status="todo")

    # 1. session_start
    start_resp = await session_start(
        ctx=fake_ctx,
        sync_svc=fake_sync,
        notion=fake_notion,
        t_state_repo=task_state_repo,
        t_repo=task_repo,
        m_repo=meeting_repo,
        closer=session_closer,
    )
    assert start_resp.session_id is not None
    assert isinstance(start_resp.open_tasks, list)
    session_id = start_resp.session_id

    # 2. task_start
    ts_resp = await task_start(
        ctx=fake_ctx,
        task_id=task.id,
        t_repo=task_repo,
        n_repo=note_repo,
    )
    assert ts_resp.task.id == task.id
    assert ts_resp.compounding is False
    initial_note_count = sum(ts_resp.notes_by_type.values())

    # 3. save_note
    note_resp = await save_note(
        ctx=fake_ctx,
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="Found the root cause in the OAuth flow",
        t_repo=task_repo,
        sec=security,
        n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    assert note_resp.note_id is not None

    # 4. task_start again -- note count should increase
    ts_resp2 = await task_start(
        ctx=fake_ctx,
        task_id=task.id,
        t_repo=task_repo,
        n_repo=note_repo,
    )
    assert ts_resp2.compounding is True
    assert sum(ts_resp2.notes_by_type.values()) == initial_note_count + 1

    # 5. what_am_i_missing
    missing_resp = await what_am_i_missing(
        ctx=fake_ctx,
        task_id=task.id,
        t_repo=task_repo,
        n_repo=note_repo,
    )
    assert isinstance(missing_resp.signals, list)

    # 6. session_end
    end_resp = await session_end(
        ctx=fake_ctx,
        session_id=session_id,
        summary="Fixed the OAuth bug",
        intent="Bug fix",
        working_set=[task.id],
        state_delta="Identified and fixed root cause",
        open_loops=[],
        next_actions=["Deploy to staging"],
        closure_status="clean",
        sec=security,
        n_repo=note_repo,
        wb=fake_writeback,
    )
    assert end_resp.note_id is not None
    assert end_resp.session_state_saved is True
    assert end_resp.closure_status == "clean"
