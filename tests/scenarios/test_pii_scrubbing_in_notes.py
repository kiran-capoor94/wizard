"""Scenario: PII in note content gets scrubbed before storage."""

import pytest

from wizard.models import Note, NoteType
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note, task_start


@pytest.mark.asyncio
async def test_pii_scrubbed_in_notes(
    db_session, fake_ctx, fake_sync, fake_notion,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer, capture_synthesiser,
):
    task = seed_task(name="PII test task")
    await session_start(
        ctx=fake_ctx, sync_svc=fake_sync, notion=fake_notion,
        t_state_repo=task_state_repo, t_repo=task_repo, m_repo=meeting_repo,
        closer=session_closer, synthesiser=capture_synthesiser,
    )

    resp = await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Spoke to user@example.com about issue, postcode SW1A 1AA",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # Check DB directly -- PII should be scrubbed
    note = db_session.get(Note, resp.note_id)
    assert note is not None
    assert "user@example.com" not in note.content
    assert "SW1A 1AA" not in note.content
    assert "[EMAIL_1]" in note.content
    assert "[POSTCODE_1]" in note.content

    # task_start returns scrubbed content too
    ts_resp = await task_start(
        ctx=fake_ctx, task_id=task.id,
        t_repo=task_repo, n_repo=note_repo,
    )
    assert len(ts_resp.prior_notes) == 1
    assert "[EMAIL_1]" in ts_resp.prior_notes[0].content
