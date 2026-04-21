"""Scenario: mid-session background synthesis."""

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import patch

import pytest

from wizard.mid_session import MID_SESSION_TASKS
from wizard.models import WizardSession
from wizard.repositories import NoteRepository
from wizard.schemas import SynthesisResult
from wizard.security import SecurityService
from wizard.synthesis import OllamaSynthesiser
from wizard.tools.session_tools import session_end, session_start
from wizard.transcript import (
    TranscriptEntry,
    TranscriptReader,
    find_transcript,
    read_new_lines,
)


def test_find_transcript_finds_file(tmp_path, monkeypatch):
    session_id = "aaaabbbb-cccc-dddd-eeee-ffff00001234"
    project_dir = tmp_path / ".claude" / "projects" / "my-project"
    project_dir.mkdir(parents=True)
    transcript = project_dir / f"{session_id}.jsonl"
    transcript.write_text("")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = find_transcript(session_id)
    assert result == transcript


def test_find_transcript_returns_none_when_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert find_transcript("nonexistent-session-uuid") is None


def test_read_new_lines_skips_processed_and_drops_last(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"line":1}\n{"line":2}\n{"line":3}\n{"line":4}\n')
    # Skip 2 already-processed, get lines 3+4 minus the last (safety guard)
    lines = read_new_lines(f, skip=2)
    assert lines == ['{"line":3}']


def test_read_new_lines_returns_empty_when_nothing_new(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"line":1}\n{"line":2}\n')
    assert read_new_lines(f, skip=2) == []


def test_read_new_lines_defers_single_new_line(tmp_path):
    # A single new line may be incomplete — defer until next poll
    f = tmp_path / "t.jsonl"
    f.write_text('{"line":1}\n{"line":2}\n')
    assert read_new_lines(f, skip=1) == []


def test_synthesise_lines_calls_synthesise_path(db_session, note_repo, security):
    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    synthesiser = OllamaSynthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
    )

    received_paths = []

    def capture(db, session, path):
        received_paths.append(path)
        return SynthesisResult(notes_created=0, task_ids_touched=[], synthesised_via="fallback")

    with patch.object(synthesiser, "synthesise_path", side_effect=capture):
        synthesiser.synthesise_lines(
            db_session,
            wizard_session,
            ['{"type":"user","message":{"content":"hi"}}'],
        )

    assert len(received_paths) == 1
    assert isinstance(received_paths[0], Path)
    assert not received_paths[0].exists()  # temp file cleaned up


@pytest.mark.asyncio
async def test_mid_session_task_registered_when_agent_session_id_provided(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security, session_closer,
):
    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001111"
    await session_start(
        ctx=fake_ctx,
        agent_session_id=agent_id,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    task = MID_SESSION_TASKS.get(agent_id)
    assert task is not None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    MID_SESSION_TASKS.pop(agent_id, None)


@pytest.mark.asyncio
async def test_mid_session_task_not_registered_without_agent_session_id(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer,
):
    before = set(MID_SESSION_TASKS.keys())
    await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert set(MID_SESSION_TASKS.keys()) == before


@pytest.mark.asyncio
async def test_mid_session_task_cancelled_on_session_end(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security, session_closer,
):
    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001112"
    start = await session_start(
        ctx=fake_ctx,
        agent_session_id=agent_id,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert agent_id in MID_SESSION_TASKS

    await session_end(
        ctx=fake_ctx,
        session_id=start.session_id,
        summary="Done",
        intent="Test",
        working_set=[],
        state_delta="",
        open_loops=[],
        next_actions=[],
        closure_status="clean",
        sec=security,
        n_repo=note_repo,
    )
    assert agent_id not in MID_SESSION_TASKS


@pytest.mark.asyncio
async def test_auto_close_cancels_mid_session_task(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer,
):
    """Auto-closing an abandoned session must clean up its mid-session task."""
    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001113"

    # Session 1: start with agent_session_id — registers a task in MID_SESSION_TASKS
    start1 = await session_start(
        ctx=fake_ctx,
        agent_session_id=agent_id,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert agent_id in MID_SESSION_TASKS
    start1_session_id = start1.session_id

    # Session 2: new start without ending session 1 — triggers auto-close of session 1
    fresh_ctx = type(fake_ctx)()
    start2 = await session_start(
        ctx=fresh_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert start2.session_id is not None

    # Mid-session task for the abandoned session must have been cleaned up
    assert agent_id not in MID_SESSION_TASKS

    # The abandoned session must have been auto-closed by SessionCloser
    session1 = db_session.get(WizardSession, start1_session_id)
    assert session1 is not None
    db_session.refresh(session1)
    assert session1.closed_by == "auto"


@pytest.mark.asyncio
async def test_session_start_sets_agent_claude_code(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer,
):
    """session_start must set session.agent = 'claude-code' for mid-session synthesis to work."""
    agent_id = "aaaabbbb-cccc-dddd-eeee-ffff00001114"
    response = await session_start(
        ctx=fake_ctx,
        agent_session_id=agent_id,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    session = db_session.get(WizardSession, response.session_id)
    assert session is not None
    assert session.agent == "claude-code"

    # Cleanup the background task
    task = MID_SESSION_TASKS.pop(agent_id, None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_session_start_without_agent_session_id_leaves_agent_none(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer,
):
    """session_start without agent_session_id must not stamp agent='claude-code'."""
    response = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    session = db_session.get(WizardSession, response.session_id)
    assert session is not None
    assert session.agent is None


# ---------------------------------------------------------------------------
# _filter_for_synthesis behaviour tests
# ---------------------------------------------------------------------------

def _make_synthesiser() -> OllamaSynthesiser:
    return OllamaSynthesiser(
        reader=TranscriptReader(),
        note_repo=NoteRepository(),
        security=SecurityService(allowlist=[], enabled=False),
    )


def test_filter_drops_read_tool_result():
    entries = [
        TranscriptEntry(role="tool_call", content="{}", tool_name="Read", tool_use_id="tu_1"),
        TranscriptEntry(role="tool_result", content="file body", tool_use_id="tu_1"),
    ]
    result = _make_synthesiser()._filter_for_synthesis(entries)
    assert len(result) == 1
    assert result[0].role == "tool_call"


def test_filter_keeps_bash_tool_result():
    entries = [
        TranscriptEntry(role="tool_call", content="{}", tool_name="Bash", tool_use_id="tu_1"),
        TranscriptEntry(role="tool_result", content="tests passed", tool_use_id="tu_1"),
    ]
    result = _make_synthesiser()._filter_for_synthesis(entries)
    assert len(result) == 2
    assert result[1].content == "tests passed"


def test_filter_batched_calls_matched_by_id():
    """Read result is dropped, Bash result kept, even when batched in one turn."""
    entries = [
        TranscriptEntry(role="tool_call", content="{}", tool_name="Read", tool_use_id="tu_1"),
        TranscriptEntry(role="tool_call", content="{}", tool_name="Bash", tool_use_id="tu_2"),
        TranscriptEntry(role="tool_result", content="file body", tool_use_id="tu_1"),
        TranscriptEntry(role="tool_result", content="tests passed", tool_use_id="tu_2"),
    ]
    result = _make_synthesiser()._filter_for_synthesis(entries)
    assert sum(1 for e in result if e.role == "tool_call") == 2
    assert not any(e.role == "tool_result" and e.content == "file body" for e in result)
    assert any(e.role == "tool_result" and e.content == "tests passed" for e in result)


def test_filter_orphaned_result_kept_conservatively():
    """tool_result with no matching tool_call (no id) is kept — safe default."""
    entries = [TranscriptEntry(role="tool_result", content="orphaned")]
    result = _make_synthesiser()._filter_for_synthesis(entries)
    assert len(result) == 1


def test_filter_truncates_per_role():
    entries = [
        TranscriptEntry(role="assistant", content="a" * 3000),
        TranscriptEntry(role="tool_call", content="{}" + "x" * 600, tool_name="Bash"),
        TranscriptEntry(role="tool_result", content="r" * 500),
    ]
    result = _make_synthesiser()._filter_for_synthesis(entries)
    assert len(result[0].content) == 1000
    assert len(result[1].content) == 250
    assert len(result[2].content) == 150
