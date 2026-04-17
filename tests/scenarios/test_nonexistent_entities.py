"""Scenario: all tools raise ToolError when given nonexistent IDs."""

import pytest
from fastmcp.exceptions import ToolError

from wizard.models import NoteType, TaskStatus
from wizard.tools.meeting_tools import get_meeting, save_meeting_summary
from wizard.tools.session_tools import session_end
from wizard.tools.task_tools import (
    rewind_task,
    save_note,
    task_start,
    update_task,
    what_am_i_missing,
)


@pytest.mark.asyncio
async def test_task_start_nonexistent(db_session, fake_ctx, task_repo, note_repo):
    with pytest.raises(ToolError):
        await task_start(ctx=fake_ctx, task_id=9999, t_repo=task_repo, n_repo=note_repo)


@pytest.mark.asyncio
async def test_save_note_nonexistent(
    db_session, fake_ctx, task_repo, note_repo, task_state_repo, security,
):
    with pytest.raises(ToolError):
        await save_note(
            ctx=fake_ctx, task_id=9999, note_type=NoteType.INVESTIGATION,
            content="test", t_repo=task_repo, sec=security,
            n_repo=note_repo, t_state_repo=task_state_repo,
        )


@pytest.mark.asyncio
async def test_update_task_nonexistent(
    db_session, fake_ctx, task_repo, task_state_repo, security, fake_writeback,
):
    with pytest.raises(ToolError):
        await update_task(
            ctx=fake_ctx, task_id=9999, status=TaskStatus.DONE,
            t_repo=task_repo, sec=security,
            t_state_repo=task_state_repo, wb=fake_writeback,
        )


@pytest.mark.asyncio
async def test_rewind_task_nonexistent(db_session, fake_ctx, note_repo):
    with pytest.raises(ToolError):
        await rewind_task(ctx=fake_ctx, task_id=9999, n_repo=note_repo)


@pytest.mark.asyncio
async def test_what_am_i_missing_nonexistent(db_session, fake_ctx, task_repo, note_repo):
    with pytest.raises(ToolError):
        await what_am_i_missing(ctx=fake_ctx, task_id=9999, t_repo=task_repo, n_repo=note_repo)


@pytest.mark.asyncio
async def test_session_end_nonexistent(db_session, fake_ctx, note_repo, security, fake_writeback):
    with pytest.raises(ToolError):
        await session_end(
            ctx=fake_ctx, session_id=9999,
            summary="test", intent="test", working_set=[],
            state_delta="test", open_loops=[], next_actions=[],
            closure_status="clean",
            sec=security, n_repo=note_repo, wb=fake_writeback,
        )


@pytest.mark.asyncio
async def test_get_meeting_nonexistent(db_session, fake_ctx, meeting_repo, task_repo):
    with pytest.raises(ToolError):
        await get_meeting(
            ctx=fake_ctx, meeting_id=9999,
            m_repo=meeting_repo, t_repo=task_repo,
        )


@pytest.mark.asyncio
async def test_save_meeting_summary_nonexistent(
    db_session, fake_ctx, meeting_repo, note_repo, security, fake_writeback,
):
    with pytest.raises(ToolError):
        await save_meeting_summary(
            ctx=fake_ctx, meeting_id=9999, summary="test",
            m_repo=meeting_repo, sec=security,
            n_repo=note_repo, wb=fake_writeback,
        )
