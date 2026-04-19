"""Scenario: calling session_end twice on the same session."""

import pytest

from wizard.tools.session_tools import session_end, session_start


@pytest.mark.asyncio
async def test_session_end_twice(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    session_closer,
):
    start_resp = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session_id = start_resp.session_id

    end_kwargs = dict(
        ctx=fake_ctx, session_id=session_id,
        summary="First end", intent="test",
        working_set=[], state_delta="done",
        open_loops=[], next_actions=[],
        closure_status="clean",
        sec=security, n_repo=note_repo,
    )

    resp1 = await session_end(**end_kwargs)
    assert resp1.note_id is not None

    # Second end on same session -- documents current behaviour
    # (currently succeeds and creates a second summary note)
    end_kwargs["summary"] = "Second end"
    resp2 = await session_end(**end_kwargs)
    assert resp2.note_id is not None
    assert resp2.note_id != resp1.note_id
