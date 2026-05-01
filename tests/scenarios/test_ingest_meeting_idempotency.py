"""Scenario: ingest_meeting with the same source_id is idempotent."""

from sqlmodel import select

from wizard.models import Meeting


class TestIngestMeetingIdempotency:
    async def test_second_call_returns_already_existed(self, mcp_client):
        args = {
            "title": "Sprint Planning",
            "content": "We discussed the roadmap.",
            "source_id": "krisp-abc-123",
        }
        first = await mcp_client.call_tool("ingest_meeting", args)
        assert not first.is_error

        second = await mcp_client.call_tool("ingest_meeting", args)
        assert not second.is_error
        assert second.structured_content["already_existed"] is True

    async def test_second_call_creates_no_duplicate_row(self, mcp_client, db_session):
        args = {
            "title": "Retro",
            "content": "What went well.",
            "source_id": "krisp-retro-001",
        }
        await mcp_client.call_tool("ingest_meeting", args)
        await mcp_client.call_tool("ingest_meeting", args)

        rows = db_session.exec(
            select(Meeting).where(Meeting.source_id == "krisp-retro-001")
        ).all()
        assert len(rows) == 1

    async def test_second_call_returns_same_meeting_id(self, mcp_client):
        args = {
            "title": "Design Review",
            "content": "Discussed API shape.",
            "source_id": "krisp-design-007",
        }
        first = await mcp_client.call_tool("ingest_meeting", args)
        second = await mcp_client.call_tool("ingest_meeting", args)

        assert first.structured_content["meeting_id"] == second.structured_content["meeting_id"]

    async def test_second_call_does_not_mutate_title(self, mcp_client, db_session):
        await mcp_client.call_tool("ingest_meeting", {
            "title": "Original Title",
            "content": "Original content.",
            "source_id": "krisp-mutation-check",
        })
        await mcp_client.call_tool("ingest_meeting", {
            "title": "Mutated Title",
            "content": "Mutated content.",
            "source_id": "krisp-mutation-check",
        })

        row = db_session.exec(
            select(Meeting).where(Meeting.source_id == "krisp-mutation-check")
        ).first()
        assert row is not None
        assert "Original" in row.title

    async def test_no_source_id_always_creates_new_row(self, mcp_client):
        args = {"title": "Stand-up", "content": "Quick sync."}
        await mcp_client.call_tool("ingest_meeting", args)
        r2 = await mcp_client.call_tool("ingest_meeting", args)

        assert not r2.is_error
        assert r2.structured_content["already_existed"] is False
