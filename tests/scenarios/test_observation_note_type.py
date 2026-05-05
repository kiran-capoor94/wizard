"""Scenario: OBSERVATION note type exists and behaves correctly across the stack."""
from wizard.models import NoteType


def test_observation_note_type_exists():
    """NoteType.OBSERVATION is a valid enum value."""
    assert NoteType.OBSERVATION == "observation"
    assert NoteType("observation") is NoteType.OBSERVATION
