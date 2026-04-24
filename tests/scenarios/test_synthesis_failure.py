"""Scenario tests for synthesis artifact_id write path and failure handling (spec §9.3)."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from wizard.llm_adapters import _parse_notes
from wizard.models import Task, WizardSession
from wizard.repositories.note import NoteRepository
from wizard.schemas import SynthesisNote
from wizard.synthesis import Synthesiser
from wizard.transcript import TranscriptReader


@pytest.fixture
def synthesiser(security, note_repo):
    from wizard.config import settings
    return Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        settings=settings,
        backend={"model": "test", "base_url": None, "api_key": None},
    )


def _write_jsonl(lines: list[dict]) -> str:
    """Write a temporary JSONL transcript file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
        return f.name


class TestSynthesisSaveNotesArtifactId:
    """Test that synthesise_path correctly populates artifact_id on written notes."""

    def test_note_anchored_to_task_when_task_id_set(self, db_session, synthesiser):
        task = Task(name="synthesis target")
        db_session.add(task)
        db_session.flush()
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        tmp = _write_jsonl([{"type": "user", "content": "hello"}])
        try:
            llm_response = [SynthesisNote(task_id=task.id, note_type="investigation", content="finding")]
            with patch("wizard.synthesis.llm_complete", return_value=llm_response):
                synthesiser.synthesise_path(db_session, ws, Path(tmp), terminal=True)
        finally:
            os.unlink(tmp)

        repo = NoteRepository()
        assert task.artifact_id is not None
        saved = repo.get_notes_by_artifact_id(db_session, task.artifact_id)
        assert len(saved) == 1
        assert saved[0].artifact_id == task.artifact_id
        assert saved[0].artifact_type == "task"
        assert saved[0].task_id == task.id

    def test_note_anchored_to_session_when_no_task(self, db_session, synthesiser):
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        tmp = _write_jsonl([{"type": "user", "content": "hello"}])
        try:
            llm_response = [SynthesisNote(task_id=None, note_type="learnings", content="session-only finding")]
            with patch("wizard.synthesis.llm_complete", return_value=llm_response):
                synthesiser.synthesise_path(db_session, ws, Path(tmp), terminal=True)
        finally:
            os.unlink(tmp)

        repo = NoteRepository()
        assert ws.artifact_id is not None
        saved = repo.get_notes_by_artifact_id(db_session, ws.artifact_id)
        assert len(saved) == 1
        assert saved[0].artifact_id == ws.artifact_id
        assert saved[0].artifact_type == "session"
        assert saved[0].task_id is None

    def test_note_anchored_to_session_when_task_id_not_in_valid_set(self, db_session, synthesiser):
        """task_id not in open tasks -> falls back to session anchor."""
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        tmp = _write_jsonl([{"type": "user", "content": "hello"}])
        try:
            # LLM returns a task_id that isn't in the open-tasks table (hallucination)
            llm_response = [SynthesisNote(task_id=9999, note_type="decision", content="stray note")]
            with patch("wizard.synthesis.llm_complete", return_value=llm_response):
                synthesiser.synthesise_path(db_session, ws, Path(tmp), terminal=True)
        finally:
            os.unlink(tmp)

        repo = NoteRepository()
        assert ws.artifact_id is not None
        saved = repo.get_notes_by_artifact_id(db_session, ws.artifact_id)
        assert len(saved) == 1
        assert saved[0].artifact_type == "session"


class TestSynthesisFailureHandling:
    def test_partial_failure_leaves_marker_note(self, db_session, synthesiser):
        """LLM failure after retry writes a recoverable marker note."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(json.dumps({"type": "user", "content": "hello world"}) + "\n")
            tmp_path = f.name

        ws = WizardSession(agent="claude-code", transcript_path=tmp_path)
        db_session.add(ws)
        db_session.flush()

        try:
            with patch("wizard.synthesis.llm_complete", side_effect=Exception("LLM unreachable")):
                synthesiser.synthesise_path(db_session, ws, Path(tmp_path), terminal=True)
        finally:
            os.unlink(tmp_path)

        db_session.refresh(ws)
        assert ws.synthesis_status == "partial_failure"
        assert ws.is_synthesised is False

        repo = NoteRepository()
        notes = repo.get_notes_by_artifact_id(db_session, ws.artifact_id)
        markers = [n for n in notes if "Synthesis failed" in (n.content or "")]
        assert len(markers) >= 1
        assert markers[0].synthesis_confidence == 0.0
        assert markers[0].status == "unclassified"

    def test_empty_transcript_sets_complete_status(self, db_session, synthesiser):
        """Empty transcript completes successfully."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = f.name  # empty file

        ws = WizardSession(agent="claude-code", transcript_path=tmp_path)
        db_session.add(ws)
        db_session.flush()

        try:
            synthesiser.synthesise_path(db_session, ws, Path(tmp_path), terminal=True)
        finally:
            os.unlink(tmp_path)

        db_session.refresh(ws)
        assert ws.synthesis_status == "complete"
        assert ws.is_synthesised is True


def test_parse_notes_coerces_task_id_list_to_none():
    """LLM returns task_id as a list (ambiguous multi-task note) — must drop to None."""
    raw = json.dumps([
        {"note_type": "decision", "content": "Updated tasks.", "task_id": [177, 178, 131]}
    ])
    notes = _parse_notes(raw)
    assert len(notes) == 1
    assert notes[0].task_id is None


def test_parse_notes_coerces_empty_task_id_list_to_none():
    """LLM returns task_id as empty list — _parse_notes must coerce to None."""
    raw = json.dumps([
        {"note_type": "investigation", "content": "Some finding.", "task_id": []}
    ])
    notes = _parse_notes(raw)
    assert len(notes) == 1
    assert notes[0].task_id is None
