"""Scenario: middleware snapshots session state on every tool call."""

import pytest

from wizard.middleware import SessionStateMiddleware
from wizard.models import NoteType, WizardSession
from wizard.schemas import SessionState
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_state_snapshot_on_note_save(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer, capture_synthesiser,
):
    """After saving a note, calling snapshot_session_state should update
    last_active_at and session_state on the WizardSession."""
    task = seed_task(name="Snapshot test task")

    start = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
        capture_synthesiser=capture_synthesiser,
    )
    sid = start.session_id

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Testing middleware snapshot",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Directly call the middleware snapshot logic
    # (tests bypass the FastMCP middleware chain)
    middleware = SessionStateMiddleware()
    middleware.snapshot_session_state(db_session, sid)

    session = db_session.get(WizardSession, sid)
    assert session.last_active_at is not None
    assert session.session_state is not None

    state = SessionState.model_validate_json(session.session_state)
    assert state.closure_status == "interrupted"
    assert task.id in state.working_set
