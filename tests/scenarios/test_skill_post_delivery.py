"""Scenario: SKILL-POST.md is read for tool response injection,
SKILL.md is read for registered-skill delivery — they are independent.
"""

import json

import wizard.agent_registration as ar
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
    (skill_dir / "SKILL.md").write_text("## Pre-call guidance")

    monkeypatch.setattr("wizard.skills._INSTALLED_SKILLS", tmp_path)
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


async def test_session_start_skill_instructions_contains_post_call_content(mcp_client):
    """session_start must inject SKILL-POST.md content, not full SKILL.md.

    SKILL-POST.md starts with '# Session Start — Post-Call Guidance'.
    The pre-call SKILL.md starts with '# Session Start' and contains the Role section.
    After the split, skill_instructions must come from SKILL-POST.md.
    """
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    d = r.structured_content
    assert d["skill_instructions"] is not None
    assert "Post-Call Guidance" in d["skill_instructions"], (
        "skill_instructions must be from SKILL-POST.md, not the full SKILL.md"
    )
    assert "## Role" not in d["skill_instructions"], (
        "Role section belongs in SKILL.md (pre-call), not in tool response"
    )


def test_register_hook_installs_session_start_for_gemini(tmp_path, monkeypatch):
    """register_hook must install a SessionStart hook for Gemini."""
    config = tmp_path / "settings.json"
    monkeypatch.setitem(ar._HOOK_CONFIGS, "gemini", (config, "hooks"))

    ar.register_hook("gemini")

    data = json.loads(config.read_text())
    assert "SessionStart" in data["hooks"], "Gemini must have a SessionStart hook registered"
    assert "SessionEnd" in data["hooks"], "Gemini must still have SessionEnd registered"


def test_register_hook_installs_session_start_for_codex(tmp_path, monkeypatch):
    """register_hook must install a SessionStart hook for Codex."""
    config = tmp_path / "hooks.json"
    monkeypatch.setitem(ar._HOOK_CONFIGS, "codex", (config, "hooks"))

    ar.register_hook("codex")

    data = json.loads(config.read_text())
    assert "SessionStart" in data["hooks"], "Codex must have a SessionStart hook registered"


def test_register_hook_installs_session_start_for_copilot(tmp_path, monkeypatch):
    """register_hook must install a sessionStart hook for Copilot."""
    config = tmp_path / "config.json"
    monkeypatch.setitem(ar._HOOK_CONFIGS, "copilot", (config, "hooks"))

    ar.register_hook("copilot")

    data = json.loads(config.read_text())
    assert "sessionStart" in data["hooks"], "Copilot must have a sessionStart hook registered"


def test_deregister_hook_removes_session_start_for_gemini(tmp_path, monkeypatch):
    """deregister_hook must remove the SessionStart hook previously registered for Gemini."""
    config = tmp_path / "settings.json"
    monkeypatch.setitem(ar._HOOK_CONFIGS, "gemini", (config, "hooks"))

    ar.register_hook("gemini")
    assert "SessionStart" in json.loads(config.read_text())["hooks"]

    ar.deregister_hook("gemini")

    data = json.loads(config.read_text())
    assert not data["hooks"].get("SessionStart"), "SessionStart hook must be removed for Gemini"


def test_deregister_hook_removes_session_start_for_codex(tmp_path, monkeypatch):
    """deregister_hook must remove the SessionStart hook previously registered for Codex."""
    config = tmp_path / "hooks.json"
    monkeypatch.setitem(ar._HOOK_CONFIGS, "codex", (config, "hooks"))

    ar.register_hook("codex")
    assert "SessionStart" in json.loads(config.read_text())["hooks"]

    ar.deregister_hook("codex")

    data = json.loads(config.read_text())
    assert not data["hooks"].get("SessionStart"), "SessionStart hook must be removed for Codex"


def test_deregister_hook_removes_session_start_for_copilot(tmp_path, monkeypatch):
    """deregister_hook must remove the sessionStart hook previously registered for Copilot."""
    config = tmp_path / "config.json"
    monkeypatch.setitem(ar._HOOK_CONFIGS, "copilot", (config, "hooks"))

    ar.register_hook("copilot")
    assert "sessionStart" in json.loads(config.read_text())["hooks"]

    ar.deregister_hook("copilot")

    data = json.loads(config.read_text())
    assert not data["hooks"].get("sessionStart"), "sessionStart hook must be removed for Copilot"
