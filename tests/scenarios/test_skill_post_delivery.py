"""Scenario: SKILL-POST.md is read for tool response injection,
SKILL.md is read for registered-skill delivery — they are independent.
"""

from wizard.skills import load_skill_post


def test_load_skill_post_returns_skill_post_md_content(tmp_path, monkeypatch):
    """load_skill_post reads SKILL-POST.md from the installed skills dir."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL-POST.md").write_text("## Post-call guidance")

    monkeypatch.setattr("wizard.skills._INSTALLED_SKILLS", tmp_path)

    result = load_skill_post("my-skill")
    assert result == "## Post-call guidance"


def test_load_skill_post_returns_none_when_file_absent(tmp_path, monkeypatch):
    """load_skill_post returns None gracefully when no SKILL-POST.md exists."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("## Pre-call guidance")  # only pre exists

    monkeypatch.setattr("wizard.skills._INSTALLED_SKILLS", tmp_path)
    # also patch package path so it doesn't find a real file
    monkeypatch.setattr("wizard.skills._PACKAGE_SKILLS", tmp_path / "nonexistent")

    result = load_skill_post("my-skill")
    assert result is None
