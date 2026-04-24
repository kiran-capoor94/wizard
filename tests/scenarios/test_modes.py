"""Scenario tests for wizard modes system."""

from wizard.config import ModesSettings, Settings
from wizard.schemas import GetModesResponse, ModeInfo, SetModeResponse


def test_modes_settings_defaults():
    """ModesSettings has sane defaults when not configured."""
    s = Settings()
    assert s.modes.default is None
    assert s.modes.allowed == []


def test_modes_settings_from_dict():
    """ModesSettings parses correctly from config values."""
    m = ModesSettings(default="socratic-mentor", allowed=["socratic-mentor"])
    assert m.default == "socratic-mentor"
    assert m.allowed == ["socratic-mentor"]


# Schema tests for Task 3


def test_mode_info_schema():
    m = ModeInfo(name="socratic-mentor", description="Staff engineer mentor mode.")
    assert m.name == "socratic-mentor"
    assert m.description == "Staff engineer mentor mode."


def test_get_modes_response_schema():
    r = GetModesResponse(
        available_modes=[ModeInfo(name="socratic-mentor", description="Mentor.")],
        active_mode="socratic-mentor",
    )
    assert len(r.available_modes) == 1
    assert r.active_mode == "socratic-mentor"


def test_set_mode_response_schema():
    r = SetModeResponse(
        active_mode="socratic-mentor",
        description="Mentor mode.",
        instruction="Invoke skill: socratic-mentor now to load this mode's behavior.",
    )
    assert r.active_mode == "socratic-mentor"
    assert r.instruction is not None


def test_set_mode_response_clear():
    """Clearing a mode returns None fields."""
    r = SetModeResponse(active_mode=None, description=None, instruction=None)
    assert r.active_mode is None
    assert r.instruction is None
