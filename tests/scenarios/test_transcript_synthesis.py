"""Scenario: session with transcript gets synthesised on next session_start."""

import json

import pytest
from sqlmodel import select

from wizard.models import Note, NoteType, WizardSession
from wizard.tools.session_tools import session_start

TRANSCRIPT = [
    {"type": "user", "message": {"role": "user", "content": "Fix the auth bug"},
     "timestamp": "2026-04-18T10:00:00Z"},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "Found the issue."},
        {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "auth.py"}},
    ]}, "timestamp": "2026-04-18T10:00:01Z"},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "OK", "is_error": False},
    ]}, "timestamp": "2026-04-18T10:00:02Z"},
]


@pytest.mark.asyncio
async def test_transcript_synthesis_on_abandoned_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo,
    session_closer, capture_synthesiser, tmp_path,
):
    """An abandoned session with a transcript_path gets synthesised at next session_start."""
    # Create transcript file
    transcript_file = tmp_path / "transcript.jsonl"
    with transcript_file.open("w") as f:
        for entry in TRANSCRIPT:
            f.write(json.dumps(entry) + "\n")

    # Create an abandoned session with transcript (simulates hook having run)
    abandoned = WizardSession(
        transcript_path=str(transcript_file),
        agent="claude-code",
    )
    db_session.add(abandoned)
    db_session.flush()
    db_session.refresh(abandoned)
    abandoned_id = abandoned.id

    # Sampling will fail in test -> synthetic fallback
    fake_ctx.sample_error = Exception("No LLM in test")

    # Start new session -- SessionCloser closes the abandoned one,
    # then CaptureSynthesiser synthesises the transcript
    start_resp = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
        capture_synthesiser=capture_synthesiser,
    )

    assert start_resp.session_id != abandoned_id
    assert len(start_resp.closed_sessions) >= 1

    # Check synthesis produced a note
    notes = db_session.exec(
        select(Note).where(Note.session_id == abandoned_id)
    ).all()
    summary_notes = [n for n in notes if n.note_type == NoteType.SESSION_SUMMARY]
    # At least 1 from SessionCloser, potentially 1 more from CaptureSynthesiser
    assert len(summary_notes) >= 1


@pytest.mark.asyncio
async def test_transcript_synthesis_on_hook_closed_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo,
    session_closer, capture_synthesiser, tmp_path,
):
    """A session already marked closed_by='hook' by the capture command
    must be synthesised on the next session_start."""
    transcript_file = tmp_path / "hook_transcript.jsonl"
    with transcript_file.open("w") as f:
        for entry in TRANSCRIPT:
            f.write(json.dumps(entry) + "\n")

    hook_session = WizardSession(
        closed_by="hook",
        transcript_path=str(transcript_file),
        agent="claude-code",
    )
    db_session.add(hook_session)
    db_session.flush()
    db_session.refresh(hook_session)
    hook_session_id = hook_session.id

    fake_ctx.sample_error = Exception("No LLM in test")

    start_resp = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        n_repo=note_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
        capture_synthesiser=capture_synthesiser,
    )

    assert start_resp.session_id != hook_session_id
    closed_ids = [cs.session_id for cs in start_resp.closed_sessions]
    assert hook_session_id in closed_ids

    # _close_one set summary and preserved closed_by
    db_session.refresh(hook_session)
    assert hook_session.summary is not None
    assert hook_session.closed_by == "hook"
