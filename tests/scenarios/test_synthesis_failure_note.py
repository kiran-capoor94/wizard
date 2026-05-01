"""Scenario: synthesis prompt instructs LLM to extract failure notes."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import select

from wizard.config import settings
from wizard.llm_adapters import parse_notes
from wizard.models import Note, NoteType, Task, WizardSession
from wizard.synthesis import Synthesiser
from wizard.synthesis_prompt import format_prompt
from wizard.transcript import TranscriptEntry, TranscriptReader


@pytest.fixture
def synthesiser(security, note_repo):
    return Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        settings=settings,
        backend={"model": "test", "base_url": None, "api_key": None},
    )


def _write_jsonl(lines: list[dict]) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
        return f.name


class TestFailureNoteExtraction:
    def test_transcript_with_failed_attempt_produces_failure_note(
        self, db_session, synthesiser
    ):
        """LLM returning a failure note_type is saved as NoteType.FAILURE."""
        task = Task(name="fix the auth bug")
        db_session.add(task)
        db_session.flush()
        ws = WizardSession(agent="claude-code")
        db_session.add(ws)
        db_session.flush()

        transcript_lines = [
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Tried monkey-patching the JWT decoder but it broke other tests."}
            ]}},
        ]
        transcript_path = _write_jsonl(transcript_lines)

        fake_response = json.dumps([{
            "note_type": "failure",
            "content": "Monkey-patching JWT decoder failed — broke integration tests for /refresh endpoint.",
            "task_id": task.id,
            "mental_model": None,
        }])

        with patch("wizard.synthesis.llm_complete", return_value=parse_notes(fake_response)):
            synthesiser.synthesise_path(db_session, ws, Path(transcript_path))

        notes = db_session.exec(select(Note).where(Note.session_id == ws.id)).all()
        assert len(notes) == 1
        assert notes[0].note_type == NoteType.FAILURE

    def test_failure_instruction_present_in_prompt(self):
        """format_prompt contains a dedicated failure instruction — not just JSON hint."""
        entries = [TranscriptEntry(role="assistant", content="did some work")]
        prompt = format_prompt(entries, task_table="")

        # Must have an explicit instruction explaining what failure notes capture,
        # not just the terse JSON format hint.
        assert "what was attempted" in prompt or "what was tried" in prompt


class TestCoerceNote:
    def test_task_id_string_integer_coerced(self):
        raw = json.dumps([{
            "note_type": "investigation",
            "content": "Found the bug.",
            "task_id": "177",
        }])
        notes = parse_notes(raw)
        assert notes[0].task_id == 177

    def test_task_id_float_coerced(self):
        raw = json.dumps([{
            "note_type": "decision",
            "content": "Chose approach A.",
            "task_id": 177.0,
        }])
        notes = parse_notes(raw)
        assert notes[0].task_id == 177

    def test_task_id_invalid_string_becomes_none(self):
        raw = json.dumps([{
            "note_type": "investigation",
            "content": "Some finding.",
            "task_id": "abc",
        }])
        notes = parse_notes(raw)
        assert notes[0].task_id is None

    def test_note_type_synonym_finding_maps_to_investigation(self):
        raw = json.dumps([{
            "note_type": "finding",
            "content": "We found something.",
            "task_id": None,
        }])
        notes = parse_notes(raw)
        assert notes[0].note_type == "investigation"

    def test_note_type_mixed_case_normalised(self):
        raw = json.dumps([{
            "note_type": " DECISION ",
            "content": "Picked option B.",
            "task_id": None,
        }])
        notes = parse_notes(raw)
        assert notes[0].note_type == "decision"

    def test_mental_model_list_joined_with_newlines(self):
        raw = json.dumps([{
            "note_type": "investigation",
            "content": "Some content.",
            "task_id": None,
            "mental_model": ["First insight.", "Second insight."],
        }])
        notes = parse_notes(raw)
        assert notes[0].mental_model == "First insight.\nSecond insight."

    def test_empty_content_note_filtered_out(self):
        raw = json.dumps([
            {"note_type": "investigation", "content": None, "task_id": None},
            {"note_type": "decision", "content": "A real decision.", "task_id": None},
        ])
        notes = parse_notes(raw)
        assert len(notes) == 1
        assert notes[0].content == "A real decision."
