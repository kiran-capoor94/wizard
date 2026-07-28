"""Scenario: ingest_meeting dual-writes a meeting episode to Graphiti on the
same spawn_background fire-and-forget seam used elsewhere, using
ALREADY-SCRUBBED content, and only on first ingest (not on idempotent re-ingest).

ingest_meeting is called directly (not via mcp_client) so a MagicMock
GraphMemoryService can be injected and asserted on -- the MCP pipeline has no
way to substitute Depends() providers per-call.
"""
import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wizard.models import MeetingCategory
from wizard.repositories import MeetingRepository
from wizard.security import SecurityService
from wizard.tools.meeting_tools import ingest_meeting


@contextmanager
def _yield_session(db):
    yield db


def _make_ctx():
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    return ctx


async def _settle_loop() -> None:
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_ingest_meeting_dual_writes_episode_to_graphiti(db_session):
    meetings_repo = MeetingRepository()
    sec = SecurityService(allowlist=[], enabled=True)
    gms = MagicMock()
    gms.push_episode = MagicMock()
    ctx = _make_ctx()

    with patch("wizard.tools.meeting_tools.get_session", lambda: _yield_session(db_session)):
        response = await ingest_meeting(
            ctx=ctx,
            title="Sprint planning",
            content="We discussed the roadmap for Q3.",
            source_id="meeting-graphiti-1",
            category=MeetingCategory.GENERAL,
            meetings_repo=meetings_repo,
            sec=sec,
            gms=gms,
        )

    assert not response.already_existed

    await _settle_loop()

    assert gms.push_episode.called
    call = gms.push_episode.call_args
    assert call.kwargs["entity_type"] == "meeting"
    assert call.kwargs["entity_id"] == response.meeting_id
    assert '"kind": "meeting"' in call.kwargs["body"]


@pytest.mark.asyncio
async def test_ingest_meeting_idempotent_reingest_does_not_push_again(db_session):
    """Re-ingesting the same source_id must not trigger a second Graphiti push."""
    meetings_repo = MeetingRepository()
    sec = SecurityService(allowlist=[], enabled=True)
    gms = MagicMock()
    gms.push_episode = MagicMock()
    ctx = _make_ctx()

    with patch("wizard.tools.meeting_tools.get_session", lambda: _yield_session(db_session)):
        first = await ingest_meeting(
            ctx=ctx,
            title="Retro",
            content="Team retro notes.",
            source_id="meeting-graphiti-2",
            category=MeetingCategory.GENERAL,
            meetings_repo=meetings_repo,
            sec=sec,
            gms=gms,
        )
        assert not first.already_existed
        await _settle_loop()
        assert gms.push_episode.call_count == 1

        second = await ingest_meeting(
            ctx=ctx,
            title="Retro",
            content="Team retro notes.",
            source_id="meeting-graphiti-2",
            category=MeetingCategory.GENERAL,
            meetings_repo=meetings_repo,
            sec=sec,
            gms=gms,
        )
        assert second.already_existed
        assert second.meeting_id == first.meeting_id

    await _settle_loop()

    assert gms.push_episode.call_count == 1
