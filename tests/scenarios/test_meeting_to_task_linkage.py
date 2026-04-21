"""Scenario: create task from meeting, verify linkage in get_meeting."""

import pytest

from wizard.models import TaskCategory, TaskPriority, TaskStatus
from wizard.tools.meeting_tools import get_meeting, ingest_meeting
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import create_task, update_task


@pytest.mark.asyncio
async def test_meeting_to_task_linkage(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    session_closer,
):
    await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    # Ingest meeting
    ingest_resp = await ingest_meeting(
        ctx=fake_ctx, title="Sprint Planning",
        content="Need to fix auth flow",
        m_repo=meeting_repo, sec=security,
    )
    meeting_id = ingest_resp.meeting_id

    # Create task linked to meeting
    create_resp = await create_task(
        name="Fix auth flow",
        priority=TaskPriority.HIGH,
        category=TaskCategory.BUG,
        meeting_id=meeting_id,
        sec=security, t_state_repo=task_state_repo,
    )
    task_id = create_resp.task_id

    # get_meeting should show linked task
    get_resp = await get_meeting(
        ctx=fake_ctx, meeting_id=meeting_id,
        m_repo=meeting_repo, t_repo=task_repo,
    )
    assert any(t.id == task_id for t in get_resp.open_tasks)

    # Mark task done -- should no longer appear in open_tasks
    await update_task(
        task_id=task_id, status=TaskStatus.DONE,
        t_repo=task_repo, sec=security,
        t_state_repo=task_state_repo,
    )
    get_resp2 = await get_meeting(
        ctx=fake_ctx, meeting_id=meeting_id,
        m_repo=meeting_repo, t_repo=task_repo,
    )
    assert not any(t.id == task_id for t in get_resp2.open_tasks)
