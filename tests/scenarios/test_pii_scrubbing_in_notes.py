"""Scenario: PII in note content gets scrubbed before storage."""

import pytest

from wizard.models import NoteType
from wizard.tools.session_tools import session_start
from wizard.tools.task_tools import save_note, task_start


@pytest.mark.asyncio
async def test_pii_scrubbed_in_notes(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer,
):
    task = await seed_task(name="PII test task")
    await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    await save_note(
        ctx=fake_ctx, task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="Spoke to user@example.com about issue, postcode SW1A 1AA",
        t_repo=task_repo, sec=security, n_repo=note_repo,
        t_state_repo=task_state_repo,
    )

    # task_start returns scrubbed content -- verify PII is gone
    ts_resp = await task_start(
        ctx=fake_ctx, task_id=task.id,
        t_repo=task_repo, n_repo=note_repo,
    )
    assert len(ts_resp.prior_notes) == 1
    note_content = ts_resp.prior_notes[0].content
    assert "user@example.com" not in note_content
    assert "SW1A 1AA" not in note_content
    assert "[EMAIL_1]" in note_content
    assert "[POSTCODE_1]" in note_content
