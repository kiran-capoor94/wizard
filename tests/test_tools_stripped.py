import pytest

from wizard.repositories import MeetingRepository
from wizard.schemas import IngestMeetingResponse, UpdateTaskResponse
from wizard.security import SecurityService
from wizard.tools.meeting_tools import ingest_meeting


def test_update_task_response_has_no_writebacks():
    for field in ("notion_write_back", "status_writeback", "due_date_writeback", "priority_writeback"):
        assert field not in UpdateTaskResponse.model_fields


@pytest.mark.asyncio
async def test_ingest_meeting_accepts_source_id(fake_ctx):
    """ingest_meeting deduplicates by explicit source_id."""
    m_repo = MeetingRepository()
    security = SecurityService()

    first = await ingest_meeting(
        ctx=fake_ctx,
        title="Sprint planning",
        content="We discussed the roadmap",
        source_id="krisp-abc123",
        source_type="KRISP",
        m_repo=m_repo,
        sec=security,
    )
    second = await ingest_meeting(
        ctx=fake_ctx,
        title="Sprint planning",
        content="We discussed the roadmap",
        source_id="krisp-abc123",
        source_type="KRISP",
        m_repo=m_repo,
        sec=security,
    )

    assert first.meeting_id == second.meeting_id
    assert second.already_existed is True


def test_ingest_meeting_response_has_no_writeback():
    assert "notion_write_back" not in IngestMeetingResponse.model_fields
