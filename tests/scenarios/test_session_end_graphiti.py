"""Scenario: session_end dual-writes a session episode to Graphiti on the same
spawn_background fire-and-forget seam used elsewhere (write_embedding,
push_note_episode), using ALREADY-SCRUBBED content.

session_end is called directly (not via mcp_client) so a MagicMock
GraphMemoryService can be injected and asserted on -- the MCP pipeline has no
way to substitute Depends() providers per-call.
"""
import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wizard.models import WizardSession
from wizard.repositories import NoteRepository
from wizard.security import SecurityService
from wizard.tools.session_tools import session_end


@contextmanager
def _yield_session(db):
    yield db


def _make_ctx():
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=None)
    ctx.set_state = AsyncMock()
    ctx.delete_state = AsyncMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


async def _settle_loop() -> None:
    # spawn_background schedules the coroutine on the running loop -- it does
    # not execute synchronously. Let the loop drain before asserting.
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_session_end_dual_writes_episode_to_graphiti(db_session):
    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)
    assert session.id is not None

    gms = MagicMock()
    gms.push_episode = MagicMock()
    n_repo = NoteRepository()
    sec = SecurityService(allowlist=[], enabled=True)
    ctx = _make_ctx()

    with patch("wizard.tools.session_tools.get_session", lambda: _yield_session(db_session)):
        response = await session_end(
            ctx=ctx,
            session_id=session.id,
            summary="Wrapped up the Graphiti dual-write task.",
            intent="Ship the session_end dual-write.",
            working_set=[],
            state_delta="Implemented push_session_episode helper.",
            open_loops=["Write the meeting-side test"],
            next_actions=["Run full suite"],
            closure_status="clean",
            sec=sec,
            n_repo=n_repo,
            gms=gms,
        )

    assert response.note_id is not None

    await _settle_loop()

    assert gms.push_episode.called
    call = gms.push_episode.call_args
    assert call.kwargs["entity_type"] == "session"
    assert call.kwargs["entity_id"] == session.id
    assert '"kind": "session"' in call.kwargs["body"]


@pytest.mark.asyncio
async def test_session_end_pushes_scrubbed_not_raw_pii(db_session):
    """summary/state_delta containing PII must be scrubbed before reaching the
    Graphiti episode body -- session_end must never push raw PII."""
    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)
    assert session.id is not None

    gms = MagicMock()
    gms.push_episode = MagicMock()
    n_repo = NoteRepository()
    sec = SecurityService(allowlist=[], enabled=True)
    ctx = _make_ctx()

    raw_email = "jane.doe@example.com"

    with patch("wizard.tools.session_tools.get_session", lambda: _yield_session(db_session)):
        await session_end(
            ctx=ctx,
            session_id=session.id,
            summary=f"Discussed rollout with {raw_email}.",
            intent="Ship the feature",
            working_set=[],
            state_delta=f"Contacted {raw_email} about the rollout plan.",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=sec,
            n_repo=n_repo,
            gms=gms,
        )

    await _settle_loop()

    assert gms.push_episode.called
    body = gms.push_episode.call_args.kwargs["body"]
    assert raw_email not in body
    assert "[EMAIL_1]" in body
