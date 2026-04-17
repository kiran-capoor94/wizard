"""Tests for wizard.skills.load_skill."""

from unittest.mock import patch

from wizard.skills import load_skill


def test_load_skill_from_installed(tmp_path):
    """load_skill returns content from the installed skills directory."""
    skill_dir = tmp_path / "session-start"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("# Session Start Skill", encoding="utf-8")

    with patch("wizard.skills._INSTALLED_SKILLS", tmp_path):
        result = load_skill("session-start")

    assert result == "# Session Start Skill"


def test_load_skill_falls_back_to_package(tmp_path):
    """load_skill falls back to package dir when installed dir has no match."""
    installed = tmp_path / "installed"
    installed.mkdir()
    package = tmp_path / "package"
    package.mkdir()

    skill_dir = package / "task-start"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("# Task Start Skill", encoding="utf-8")

    with (
        patch("wizard.skills._INSTALLED_SKILLS", installed),
        patch("wizard.skills._PACKAGE_SKILLS", package),
    ):
        result = load_skill("task-start")

    assert result == "# Task Start Skill"


def test_load_skill_returns_none_when_not_found(tmp_path):
    """load_skill returns None when skill is not in either directory."""
    with (
        patch("wizard.skills._INSTALLED_SKILLS", tmp_path / "a"),
        patch("wizard.skills._PACKAGE_SKILLS", tmp_path / "b"),
    ):
        result = load_skill("nonexistent")

    assert result is None


def test_load_skill_returns_none_on_oserror(tmp_path):
    """load_skill returns None and logs warning when file read fails."""
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("content", encoding="utf-8")
    # Make the file unreadable
    skill_file.chmod(0o000)

    try:
        with patch("wizard.skills._INSTALLED_SKILLS", tmp_path):
            result = load_skill("broken")
        assert result is None
    finally:
        skill_file.chmod(0o644)


def test_load_skill_prefers_installed_over_package(tmp_path):
    """When both dirs have the skill, installed wins."""
    installed = tmp_path / "installed"
    package = tmp_path / "package"
    for d in (installed, package):
        skill_dir = d / "note"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# From {d.name}", encoding="utf-8")

    with (
        patch("wizard.skills._INSTALLED_SKILLS", installed),
        patch("wizard.skills._PACKAGE_SKILLS", package),
    ):
        result = load_skill("note")

    assert result == "# From installed"
