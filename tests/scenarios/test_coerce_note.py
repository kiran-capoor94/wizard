"""Scenario: _coerce_note handles LLM schema quirks defensively."""

import json

from wizard.llm_adapters import parse_notes


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

    def test_note_type_mixed_case_and_whitespace_normalised(self):
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
