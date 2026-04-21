"""Scenario: saving the exact same note twice -- both should persist."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note, task_start


@pytest.mark.asyncio
async def test_duplicate_notes(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = await seed_task(name="Dupe notes task")
    await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    content = "Found the bug in auth"
    resp1 = await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content=content,
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    resp2 = await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content=content,
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    assert resp1.note_id != resp2.note_id  # two distinct notes

    ts_resp = await task_start(
        ctx=fake_ctx, task_id=task.id,
        t_repo=task_repo, n_repo=note_repo,
    )
    assert sum(ts_resp.notes_by_type.values()) == 2
