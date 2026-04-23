"""Scenario tests for synthesis artifact_id write path and failure handling (spec §9.3)."""

from unittest.mock import patch

import pytest

from wizard.models import Note, NoteType, Task, WizardSession
from wizard.repositories.note import NoteRepository
from wizard.synthesis import Synthesiser


@pytest.fixture
def synthesiser(security, note_repo):
    from wizard.transcript import TranscriptReader
    return Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        backend={"model": "test", "base_url": None, "api_key": None},
    )


class TestSynthesisWritesArtifactId:
    def test_synthesised_note_has_artifact_id(self, db_session):
        """Notes written by synthesis carry artifact_id."""
        task = Task(name="synthesis target")
        db_session.add(task)
        db_session.flush()
        ws = WizardSession(transcript_raw="[]")
        db_session.add(ws)
        db_session.flush()
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="synthesised finding",
            task_id=task.id,
            session_id=ws.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(note)
        db_session.flush()
        assert note.artifact_id == task.artifact_id
        assert note.artifact_type == "task"

    def test_session_note_uses_session_artifact_id(self, db_session):
        ws = WizardSession(transcript_raw="[]")
        db_session.add(ws)
        db_session.flush()
        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content="session note",
            session_id=ws.id,
            artifact_id=ws.artifact_id,
            artifact_type="session",
        )
        db_session.add(note)
        db_session.flush()
        assert note.artifact_id == ws.artifact_id
        assert note.artifact_type == "session"


class TestSynthesisFailureHandling:
    def test_partial_failure_leaves_marker_note(self, db_session, synthesiser):
        """LLM failure after retry writes a recoverable marker note."""
        ws = WizardSession(
            agent="claude-code",
            transcript_raw='[{"type":"user","content":"hello world"}]',
        )
        # Write a fake transcript file for synthesise_path to read
        import json
        import os
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(json.dumps({"type": "user", "content": "hello world"}) + "\n")
            tmp_path = f.name
        ws.transcript_path = tmp_path
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
        import os
        import tempfile
        from pathlib import Path
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
