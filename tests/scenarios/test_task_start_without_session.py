"""Scenario: calling task_start and save_note without session_start."""

import pytest

from wizard.models import Note, NoteType
from wizard.tools.task_tools import task_start, save_note


@pytest.mark.asyncio
async def test_task_start_without_session(
    db_session, fake_ctx, task_repo, note_repo, task_state_repo, security,
    seed_task,
):
    """task_start works without a session -- it doesn't require one."""
    task = seed_task(name="Orphan task")

    resp = await task_start(
        ctx=fake_ctx, task_id=task.id,
        t_repo=task_repo, n_repo=note_repo,
    )
    assert resp.task.id == task.id


@pytest.mark.asyncio
async def test_save_note_without_session(
    db_session, fake_ctx, task_repo, note_repo, task_state_repo, security,
    seed_task,
):
    """save_note without session_start: note is saved with session_id=None."""
    task = seed_task(name="Orphan task for notes")

    resp = await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Working without a session",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    assert resp.note_id is not None

    # Verify note has no session_id
    note = db_session.get(Note, resp.note_id)
    assert note is not None
    assert note.session_id is None
