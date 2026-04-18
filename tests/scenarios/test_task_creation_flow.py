"""Scenario: create task, update, save notes, rewind."""

import pytest

from wizard.models import NoteType, TaskCategory, TaskPriority, TaskStatus
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import (
    create_task,
    rewind_task,
    save_note,
    update_task,
)


@pytest.mark.asyncio
async def test_task_creation_flow(
    db_session, fake_ctx, fake_sync, fake_notion, fake_writeback,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    session_closer, capture_synthesiser,
):
    # Start session
    await session_start(
        ctx=fake_ctx, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
        closer=session_closer, synthesiser=capture_synthesiser,
    )

    # 1. create_task
    create_resp = await create_task(
        ctx=fake_ctx,
        name="Fix login bug",
        priority=TaskPriority.HIGH,
        category=TaskCategory.BUG,
        sec=security,
        t_state_repo=task_state_repo,
        wb=fake_writeback,
    )
    task_id = create_resp.task_id
    assert task_id is not None

    # 2. update_task -- status to in_progress
    update_resp = await update_task(
        ctx=fake_ctx,
        task_id=task_id,
        status=TaskStatus.IN_PROGRESS,
        t_repo=task_repo,
        sec=security,
        t_state_repo=task_state_repo,
        wb=fake_writeback,
    )
    assert "status" in update_resp.updated_fields

    # 3. save_note
    await save_note(
        ctx=fake_ctx, task_id=task_id, note_type=NoteType.DECISION,
        content="Going with OAuth2",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # 4. update_task -- done
    done_resp = await update_task(
        ctx=fake_ctx,
        task_id=task_id,
        status=TaskStatus.DONE,
        t_repo=task_repo,
        sec=security,
        t_state_repo=task_state_repo,
        wb=fake_writeback,
    )
    assert "status" in done_resp.updated_fields

    # 5. rewind_task -- should show timeline
    rewind_resp = await rewind_task(
        ctx=fake_ctx, task_id=task_id, n_repo=note_repo,
    )
    assert rewind_resp.summary.total_notes == 1
    assert len(rewind_resp.timeline) == 1
    assert rewind_resp.timeline[0].note_type == NoteType.DECISION
