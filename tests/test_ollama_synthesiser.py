"""Tests for OllamaSynthesiser -- mocks ollama.Client to avoid a live Ollama server."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlmodel import select

from wizard.models import Note, NoteType, WizardSession
from wizard.repositories import NoteRepository
from wizard.security import SecurityService
from wizard.transcript import OllamaSynthesiser, TranscriptEntry, TranscriptReader


def _make_ollama_response(notes: list[dict]) -> MagicMock:
    response = MagicMock()
    response.message.content = json.dumps(notes)
    return response


def _make_synthesiser() -> OllamaSynthesiser:
    return OllamaSynthesiser(
        reader=TranscriptReader(),
        note_repo=NoteRepository(),
        security=SecurityService(),
    )


_FAKE_ENTRIES = [
    TranscriptEntry(role="user", content="Fix the auth bug"),
    TranscriptEntry(role="assistant", content="Found the issue in auth.py"),
    TranscriptEntry(role="tool_call", content='{"file_path": "auth.py"}', tool_name="Edit"),
]

_FAKE_NOTES = [
    {
        "task_id": None,
        "note_type": "investigation",
        "content": "Found auth bug in auth.py on line 42",
        "mental_model": "Auth fails because token validation skips expiry check.",
    },
    {
        "task_id": None,
        "note_type": "decision",
        "content": "Fixed by adding expiry check before returning True",
        "mental_model": None,
    },
]


def _fake_ollama_response():
    """Minimal valid Ollama response for synthesis tests."""
    from wizard.transcript import SynthesisNote
    note = SynthesisNote(
        note_type="investigation",
        content="Investigated X.",
        task_id=None,
        mental_model=None,
    )
    resp = MagicMock()
    resp.message.content = f'[{note.model_dump_json()}]'
    return resp


def test_synthesise_saves_notes(db_session):
    session = WizardSession(transcript_path="/tmp/t.jsonl", agent="claude-code")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    fake_response = _make_ollama_response(_FAKE_NOTES)

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES), \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.return_value = fake_response
        result = _make_synthesiser().synthesise(db_session, session)

    assert result.notes_created == 2
    assert result.synthesised_via == "ollama"
    assert session.is_synthesised is True
    assert session.summary is not None

    notes = list(db_session.execute(select(Note).where(Note.session_id == session.id)).scalars())
    assert len(notes) == 2
    assert notes[0].note_type == NoteType.INVESTIGATION
    assert notes[1].note_type == NoteType.DECISION


def test_synthesise_sets_summary_if_absent(db_session):
    session = WizardSession(transcript_path="/tmp/t.jsonl", agent="claude-code", summary=None)
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES), \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.return_value = _make_ollama_response(_FAKE_NOTES)
        _make_synthesiser().synthesise(db_session, session)

    assert session.summary is not None


def test_synthesise_preserves_existing_summary(db_session):
    session = WizardSession(
        transcript_path="/tmp/t.jsonl", agent="claude-code", summary="user summary",
    )
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES), \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.return_value = _make_ollama_response(_FAKE_NOTES)
        _make_synthesiser().synthesise(db_session, session)

    assert session.summary == "user summary"


def test_synthesise_returns_fallback_when_no_transcript(db_session):
    session = WizardSession(transcript_path=None, agent="claude-code")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    result = _make_synthesiser().synthesise(db_session, session)

    assert result.notes_created == 0
    assert result.synthesised_via == "fallback"
    assert session.is_synthesised is False


def test_synthesise_returns_fallback_when_empty_transcript(db_session):
    session = WizardSession(transcript_path="/tmp/t.jsonl", agent="claude-code")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    with patch.object(TranscriptReader, "read", return_value=[]):
        result = _make_synthesiser().synthesise(db_session, session)

    assert result.notes_created == 0
    assert result.synthesised_via == "fallback"


def test_synthesise_returns_fallback_on_ollama_error(db_session):
    session = WizardSession(transcript_path="/tmp/t.jsonl", agent="claude-code")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES), \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.side_effect = Exception("connection refused")
        result = _make_synthesiser().synthesise(db_session, session)

    assert result.notes_created == 0
    assert result.synthesised_via == "fallback"
    assert session.is_synthesised is False
    assert session.summary is None


def test_task_ids_always_null(db_session):
    """OllamaSynthesiser never sets task_id -- wizard owns task matching."""
    session = WizardSession(transcript_path="/tmp/t.jsonl", agent="claude-code")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    notes_with_task_id = [
        {"task_id": 99, "note_type": "investigation", "content": "test", "mental_model": None},
    ]

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES), \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.return_value = _make_ollama_response(notes_with_task_id)
        result = _make_synthesiser().synthesise(db_session, session)

    assert result.task_ids_touched == []
    notes = list(db_session.execute(select(Note).where(Note.session_id == session.id)).scalars())
    assert all(n.task_id is None for n in notes)


def test_synthesise_path_ignores_session_transcript_path(db_session):
    """synthesise_path must use its explicit path arg, not session.transcript_path."""
    session = WizardSession(agent="claude-code")  # transcript_path is None
    db_session.add(session)
    db_session.flush()

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES) as mock_read, \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.return_value = _fake_ollama_response()
        result = _make_synthesiser().synthesise_path(
            db_session, session, Path("/explicit/path.jsonl")
        )

    mock_read.assert_called_once_with("/explicit/path.jsonl", "claude-code")
    assert result.synthesised_via == "ollama"


def test_synthesise_delegates_to_synthesise_path(db_session):
    """`synthesise()` calls `synthesise_path()` with `session.transcript_path`."""
    session = WizardSession(
        transcript_path="/stored/path.jsonl", agent="claude-code"
    )
    db_session.add(session)
    db_session.flush()

    with patch.object(TranscriptReader, "read", return_value=_FAKE_ENTRIES) as mock_read, \
         patch("wizard.transcript.ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.chat.return_value = _fake_ollama_response()
        result = _make_synthesiser().synthesise(db_session, session)

    mock_read.assert_called_once_with("/stored/path.jsonl", "claude-code")
    assert result.synthesised_via == "ollama"
