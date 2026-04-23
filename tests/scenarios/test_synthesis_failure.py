"""Scenario tests for synthesis artifact_id write path and failure handling (spec §9.3)."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from wizard.models import Task, WizardSession
from wizard.repositories.note import NoteRepository
from wizard.schemas import SynthesisNote
from wizard.synthesis import Synthesiser
from wizard.transcript import TranscriptReader


@pytest.fixture
def synthesiser(security, note_repo):
    return Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        backend={"model": "test", "base_url": None, "api_key": None},
    )


class TestSynthesisSaveNotesArtifactId:
    """Test that _save_notes correctly populates artifact_id on written notes."""

    def test_note_anchored_to_task_when_task_id_set(self, db_session, synthesiser):
        task = Task(name="synthesis target")
        db_session.add(task)
        db_session.flush()
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        notes_data = [SynthesisNote(task_id=task.id, note_type="investigation", content="finding")]
        synthesiser._save_notes(db_session, notes_data, ws, valid_task_ids={task.id})

        repo = NoteRepository()
        saved = repo.get_notes_by_artifact_id(db_session, task.artifact_id)
        assert len(saved) == 1
        assert saved[0].artifact_id == task.artifact_id
        assert saved[0].artifact_type == "task"
        assert saved[0].task_id == task.id

    def test_note_anchored_to_session_when_no_task(self, db_session, synthesiser):
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        notes_data = [SynthesisNote(task_id=None, note_type="learnings", content="session-only finding")]
        synthesiser._save_notes(db_session, notes_data, ws, valid_task_ids=set())

        repo = NoteRepository()
        saved = repo.get_notes_by_artifact_id(db_session, ws.artifact_id)
        assert len(saved) == 1
        assert saved[0].artifact_id == ws.artifact_id
        assert saved[0].artifact_type == "session"
        assert saved[0].task_id is None

    def test_note_anchored_to_session_when_task_id_not_in_valid_set(self, db_session, synthesiser):
        """task_id rejected by valid_task_ids filter -> falls back to session anchor."""
        task = Task(name="foreign task")
        db_session.add(task)
        db_session.flush()
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        notes_data = [SynthesisNote(task_id=task.id, note_type="decision", content="stray note")]
        # task.id not in valid_task_ids — should be rejected
        synthesiser._save_notes(db_session, notes_data, ws, valid_task_ids=set())

        repo = NoteRepository()
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
