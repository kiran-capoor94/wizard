"""Scenario: SKILL-POST.md is read for tool response injection,
SKILL.md is read for registered-skill delivery — they are independent.
"""

from wizard.skills import load_skill_post
import wizard.agent_registration as ar


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


def test_install_skills_excludes_skill_post_md(tmp_path, monkeypatch):
    """SKILL-POST.md must never be copied to agent skill directories."""
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    skill_dir = source / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("pre-call content")
    (skill_dir / "SKILL-POST.md").write_text("post-call content — internal only")

    monkeypatch.setitem(ar._AGENT_SKILLS_DIRS, "claude-code", dest)

    ar.install_skills("claude-code", source)

    assert (dest / "my-skill" / "SKILL.md").exists(), "SKILL.md must be installed"
    assert not (dest / "my-skill" / "SKILL-POST.md").exists(), "SKILL-POST.md must NOT be installed"
