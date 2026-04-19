"""Scenario: what_am_i_missing signals evolve as notes are added."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note, what_am_i_missing


def signal_types(resp) -> set[str]:
    return {s.type for s in resp.signals}


@pytest.mark.asyncio
async def test_signal_progression(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = seed_task(name="Signal test task")
    await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    # 1. No notes -> no_context signal
    resp = await what_am_i_missing(
        ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo,
    )
    assert "no_context" in signal_types(resp)

    # 2. One investigation -> low_context + no_decisions
    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Looking into it",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    resp = await what_am_i_missing(
        ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo,
    )
    types = signal_types(resp)
    assert "no_context" not in types
    assert "no_decisions" in types

    # 3. 4+ investigations, no decision -> analysis_loop
    for i in range(3):
        await save_note(
            ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
            content=f"Investigation round {i+2}",
            t_repo=task_repo, sec=security, n_repo=note_repo,
            t_state_repo=task_state_repo,
        )
    resp = await what_am_i_missing(
        ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo,
    )
    assert "analysis_loop" in signal_types(resp)

    # 4. Decision with mental model -> analysis_loop and no_decisions gone
    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.DECISION,
        content="Going with approach B",
        mental_model="Root cause is in the auth middleware",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    resp = await what_am_i_missing(
        ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo,
    )
    types = signal_types(resp)
    assert "analysis_loop" not in types
    assert "no_decisions" not in types
    assert "no_model" not in types
