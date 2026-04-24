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


# Task 4: build_available_modes tests

from wizard.tools.mode_tools import build_available_modes


def test_build_available_modes_filters_to_allowed(tmp_path):
    """Only skills in allowed list are returned."""
    skill_dir = tmp_path / "socratic-mentor"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: socratic-mentor\ndescription: Mentor mode.\n---\n# Content"
    )

    modes = ModesSettings(default="socratic-mentor", allowed=["socratic-mentor"])
    result = build_available_modes(modes, roots=[tmp_path])
    assert len(result) == 1
    assert result[0].name == "socratic-mentor"
    assert result[0].description == "Mentor mode."


def test_build_available_modes_empty_allowed(tmp_path):
    """Empty allowed list returns empty modes."""
    modes = ModesSettings(allowed=[])
    result = build_available_modes(modes, roots=[tmp_path])
    assert result == []


def test_build_available_modes_missing_skill(tmp_path):
    """Skill in allowed list but not found in roots is skipped silently."""
    modes = ModesSettings(allowed=["nonexistent-skill"])
    result = build_available_modes(modes, roots=[tmp_path])
    assert result == []
