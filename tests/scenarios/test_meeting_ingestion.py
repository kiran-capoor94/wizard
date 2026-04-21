"""Scenario: ingest meeting, get it, save summary, test dedup."""

import pytest

from wizard.tools.meeting_tools import get_meeting, ingest_meeting, save_meeting_summary
from wizard.tools.session_tools import session_start


@pytest.mark.asyncio
async def test_meeting_ingestion(
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

    # 1. ingest_meeting
    ingest_resp = await ingest_meeting(
        ctx=fake_ctx,
        title="Sprint Planning",
        content="Discussed Q3 priorities and assignments",
        source_id="krisp-abc123",
        source_url="https://krisp.ai/meetings/abc123",
        m_repo=meeting_repo,
        sec=security,
    )
    meeting_id = ingest_resp.meeting_id
    assert meeting_id is not None
    assert ingest_resp.already_existed is False

    # 2. get_meeting
    get_resp = await get_meeting(
        ctx=fake_ctx, meeting_id=meeting_id,
        m_repo=meeting_repo, t_repo=task_repo,
    )
    assert get_resp.title == "Sprint Planning"
    assert get_resp.already_summarised is False

    # 3. save_meeting_summary
    summary_resp = await save_meeting_summary(
        ctx=fake_ctx,
        meeting_id=meeting_id,
        summary="Agreed on Q3 priorities",
        m_repo=meeting_repo, sec=security, n_repo=note_repo,
    )
    assert summary_resp.note_id is not None

    # 4. get_meeting again -- should be summarised now
    get_resp2 = await get_meeting(
        ctx=fake_ctx, meeting_id=meeting_id,
        m_repo=meeting_repo, t_repo=task_repo,
    )
    assert get_resp2.already_summarised is True

    # 5. ingest same meeting again (dedup by source_id)
    ingest_resp2 = await ingest_meeting(
        ctx=fake_ctx,
        title="Sprint Planning (updated)",
        content="Updated content",
        source_id="krisp-abc123",
        m_repo=meeting_repo,
        sec=security,
    )
    assert ingest_resp2.already_existed is True
    assert ingest_resp2.meeting_id == meeting_id
