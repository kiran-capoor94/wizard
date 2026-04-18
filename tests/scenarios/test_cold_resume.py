"""Scenario: resume_session with no prior sessions, and with nonexistent session_id."""

import pytest
from fastmcp.exceptions import ToolError

from wizard.tools.session_tools import resume_session


@pytest.mark.asyncio
async def test_cold_resume_no_sessions(
    db_session, fake_ctx, fake_sync, fake_notion,
    task_repo, note_repo, meeting_repo,
):
    """resume_session() with no args when no sessions exist."""
    with pytest.raises(ToolError, match="No sessions with notes found"):
        await resume_session(
            ctx=fake_ctx, sync_svc=fake_sync, notion=fake_notion,
            t_repo=task_repo, n_repo=note_repo, m_repo=meeting_repo,
        )


@pytest.mark.asyncio
async def test_cold_resume_nonexistent_session(
    db_session, fake_ctx, fake_sync, fake_notion,
    task_repo, note_repo, meeting_repo,
):
    """resume_session(session_id=999) for a session that doesn't exist."""
    with pytest.raises(ToolError, match="Session 999 not found"):
        await resume_session(
            ctx=fake_ctx, session_id=999,
            sync_svc=fake_sync, notion=fake_notion,
            t_repo=task_repo, n_repo=note_repo, m_repo=meeting_repo,
        )
