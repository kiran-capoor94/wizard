"""Scenario: mid-session background synthesis."""

from pathlib import Path
from unittest.mock import patch

from wizard.models import WizardSession
from wizard.schemas import SynthesisResult
from wizard.transcript import (
    OllamaSynthesiser,
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
