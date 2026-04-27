"""Scenario tests for wizard modes system."""
from unittest.mock import MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from wizard.config import ModesSettings, Settings
from wizard.models import WizardSession
from wizard.schemas import (
    GetModesResponse,
    ModeInfo,
    ResumeSessionResponse,
    SessionStartResponse,
    SetModeResponse,
)
from wizard.tools.mode_tools import build_available_modes, get_modes, set_mode


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


# Task 5: get_modes tests


@pytest.mark.asyncio
async def test_get_modes_no_session(tmp_path):
    """get_modes returns available_modes and None active_mode when no session_id given."""

    skill_dir = tmp_path / "socratic-mentor"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: socratic-mentor\ndescription: Mentor.\n---\n"
    )

    modes_cfg = ModesSettings(default=None, allowed=["socratic-mentor"])
    with patch("wizard.tools.mode_tools.settings") as mock_settings:
        mock_settings.modes = modes_cfg
        result = await get_modes(session_id=None, skill_roots=[tmp_path])

    assert isinstance(result, GetModesResponse)
    assert len(result.available_modes) == 1
    assert result.available_modes[0].name == "socratic-mentor"
    assert result.active_mode is None


@pytest.mark.asyncio
async def test_get_modes_with_active_session(tmp_path):
    """get_modes returns active_mode from DB when session_id given."""
    skill_dir = tmp_path / "socratic-mentor"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: socratic-mentor\ndescription: Mentor.\n---\n"
    )

    mock_session_obj = MagicMock(spec=WizardSession)
    mock_session_obj.active_mode = "socratic-mentor"

    mock_s_repo = MagicMock()
    mock_s_repo.get.return_value = mock_session_obj

    modes_cfg = ModesSettings(allowed=["socratic-mentor"])
    with patch("wizard.tools.mode_tools.settings") as mock_settings, \
         patch("wizard.tools.mode_tools.get_session"):
        mock_settings.modes = modes_cfg
        result = await get_modes(session_id=42, skill_roots=[tmp_path], s_repo=mock_s_repo)

    assert result.active_mode == "socratic-mentor"
    mock_s_repo.get.assert_called_once()


# Task 6: set_mode tests


@pytest.mark.asyncio
async def test_set_mode_activates_mode(tmp_path):
    """set_mode writes active_mode to DB and returns instruction."""
    skill_dir = tmp_path / "socratic-mentor"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: socratic-mentor\ndescription: Mentor.\n---\n"
    )

    mock_s_repo = MagicMock()

    modes_cfg = ModesSettings(allowed=["socratic-mentor"])
    with patch("wizard.tools.mode_tools.settings") as mock_settings, \
         patch("wizard.tools.mode_tools.get_session"):
        mock_settings.modes = modes_cfg
        result = await set_mode(
            session_id=42,
            mode_name="socratic-mentor",
            skill_roots=[tmp_path],
            s_repo=mock_s_repo,
        )

    assert result.active_mode == "socratic-mentor"
    assert result.instruction == "Invoke skill: socratic-mentor now to load this mode's behavior."
    mock_s_repo.set_active_mode.assert_called_once()


@pytest.mark.asyncio
async def test_set_mode_clears_mode(tmp_path):
    """set_mode(mode_name=None) clears active_mode and returns None instruction."""
    mock_s_repo = MagicMock()

    modes_cfg = ModesSettings(allowed=["socratic-mentor"])
    with patch("wizard.tools.mode_tools.settings") as mock_settings, \
         patch("wizard.tools.mode_tools.get_session"):
        mock_settings.modes = modes_cfg
        result = await set_mode(
            session_id=42,
            mode_name=None,
            skill_roots=[tmp_path],
            s_repo=mock_s_repo,
        )

    assert result.active_mode is None
    assert result.instruction is None
    mock_s_repo.set_active_mode.assert_called_once()


@pytest.mark.asyncio
async def test_set_mode_rejects_unknown_mode(tmp_path):
    """set_mode raises ToolError for mode not in allowed list."""
    modes_cfg = ModesSettings(allowed=["socratic-mentor"])
    with patch("wizard.tools.mode_tools.settings") as mock_settings:
        mock_settings.modes = modes_cfg
        with pytest.raises(ToolError, match="not in allowed modes"):
            await set_mode(session_id=42, mode_name="pair-programmer", skill_roots=[tmp_path])


@pytest.mark.asyncio
async def test_set_mode_session_not_found():
    """set_mode raises ToolError when session_id does not exist."""
    mock_s_repo = MagicMock()
    mock_s_repo.set_active_mode.side_effect = ValueError("Session 99 not found")

    modes_cfg = ModesSettings(allowed=["socratic-mentor"])
    with patch("wizard.tools.mode_tools.settings") as mock_settings, \
         patch("wizard.tools.mode_tools.get_session"):
        mock_settings.modes = modes_cfg
        with pytest.raises(ToolError, match="Session 99 not found"):
            await set_mode(
                session_id=99,
                mode_name="socratic-mentor",
                s_repo=mock_s_repo,
            )



# Task 7: Wire session_start

def test_session_start_response_has_mode_fields():
    """SessionStartResponse schema accepts active_mode and available_modes fields."""
    r = SessionStartResponse(
        session_id=1,
        unsummarised_meetings=[],
        active_mode="socratic-mentor",
        available_modes=[ModeInfo(name="socratic-mentor", description="Mentor.")],
    )
    assert r.active_mode == "socratic-mentor"
    assert len(r.available_modes) == 1


# Task 8: Wire resume_session

def test_resume_session_response_has_active_mode():
    """ResumeSessionResponse schema accepts active_mode field."""
    r = ResumeSessionResponse(
        session_id=2,
        resumed_from_session_id=1,
        session_state=None,
        working_set_tasks=[],
        prior_notes=[],
        unsummarised_meetings=[],
        active_mode="socratic-mentor",
    )
    assert r.active_mode == "socratic-mentor"


# New mode skill loading tests


def test_build_available_modes_loads_architect(tmp_path):
    """build_available_modes returns correct ModeInfo for architect skill."""
    skill_dir = tmp_path / "architect"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: architect\ndescription: Principal-level systems thinker. Challenges scope before solutions, holds the whole system in mind, and ensures decisions are recorded not just made.\n---\n# Content"
    )

    modes = ModesSettings(allowed=["architect"])
    result = build_available_modes(modes, roots=[tmp_path])
    assert len(result) == 1
    assert result[0].name == "architect"
    assert result[0].description == "Principal-level systems thinker. Challenges scope before solutions, holds the whole system in mind, and ensures decisions are recorded not just made."


def test_build_available_modes_loads_ideation(tmp_path):
    """build_available_modes returns correct ModeInfo for ideation skill."""
    skill_dir = tmp_path / "ideation"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ideation\ndescription: Creative thinking partner for divergent exploration. Always elicits context first, generates ideas without filtering, challenges assumptions, and ends with a ranked recommendation and concrete next step.\n---\n# Content"
    )

    modes = ModesSettings(allowed=["ideation"])
    result = build_available_modes(modes, roots=[tmp_path])
    assert len(result) == 1
    assert result[0].name == "ideation"
    assert result[0].description == "Creative thinking partner for divergent exploration. Always elicits context first, generates ideas without filtering, challenges assumptions, and ends with a ranked recommendation and concrete next step."


def test_build_available_modes_loads_product_owner(tmp_path):
    """build_available_modes returns correct ModeInfo for product-owner skill."""
    skill_dir = tmp_path / "product-owner"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: product-owner\ndescription: Ruthless advocate for user value. Cuts technical vanity, always asks who benefits and how we know.\n---\n# Content"
    )

    modes = ModesSettings(allowed=["product-owner"])
    result = build_available_modes(modes, roots=[tmp_path])
    assert len(result) == 1
    assert result[0].name == "product-owner"
    assert result[0].description == "Ruthless advocate for user value. Cuts technical vanity, always asks who benefits and how we know."


def test_build_available_modes_loads_all_three_new_modes(tmp_path):
    """All three new modes are returned together when all are in allowed list."""
    for name, description in [
        (
            "architect",
            "Principal-level systems thinker. Challenges scope before solutions, holds the whole system in mind, and ensures decisions are recorded not just made.",
        ),
        (
            "ideation",
            "Creative thinking partner for divergent exploration. Always elicits context first, generates ideas without filtering, challenges assumptions, and ends with a ranked recommendation and concrete next step.",
        ),
        (
            "product-owner",
            "Ruthless advocate for user value. Cuts technical vanity, always asks who benefits and how we know.",
        ),
    ]:
        skill_dir = tmp_path / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n# Content"
        )

    modes = ModesSettings(allowed=["architect", "ideation", "product-owner"])
    result = build_available_modes(modes, roots=[tmp_path])

    assert len(result) == 3
    names = [r.name for r in result]
    assert "architect" in names
    assert "ideation" in names
    assert "product-owner" in names
