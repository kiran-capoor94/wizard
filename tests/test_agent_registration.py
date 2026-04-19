import json
from unittest.mock import patch

import pytest

from wizard.agent_registration import deregister_hook, register_hook


@pytest.fixture()
def tmp_settings(tmp_path):
    """A minimal ~/.claude/settings.json in a temp dir."""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {}}))
    return settings


def _hook_commands(data: dict, event: str) -> list[str]:
    """Extract all hook commands for a given event from settings data."""
    entries = data.get("hooks", {}).get(event, [])
    return [h["command"] for entry in entries for h in entry.get("hooks", [])]


def test_register_hook_claude_code_installs_both_events(tmp_settings, tmp_path):
    """register_hook for claude-code must write SessionEnd AND SessionStart entries."""
    with (
        patch("wizard.agent_registration._HOOK_CONFIGS", {
            "claude-code": (tmp_settings, "hooks"),
        }),
        patch("wizard.agent_registration._HOOK_SCRIPTS", {
            "claude-code": {
                "SessionEnd": tmp_path / "session-end.sh",
                "SessionStart": tmp_path / "session-start.sh",
            }
        }),
    ):
        result = register_hook("claude-code")

    assert result is True
    data = json.loads(tmp_settings.read_text())
    end_cmds = _hook_commands(data, "SessionEnd")
    start_cmds = _hook_commands(data, "SessionStart")
    assert any("session-end" in c for c in end_cmds)
    assert any("session-start" in c for c in start_cmds)


def test_register_hook_claude_code_is_idempotent(tmp_settings, tmp_path):
    """Calling register_hook twice must not duplicate entries."""
    hooks_patch = {
        "claude-code": {
            "SessionEnd": tmp_path / "session-end.sh",
            "SessionStart": tmp_path / "session-start.sh",
        }
    }
    with (
        patch("wizard.agent_registration._HOOK_CONFIGS", {
            "claude-code": (tmp_settings, "hooks"),
        }),
        patch("wizard.agent_registration._HOOK_SCRIPTS", hooks_patch),
    ):
        register_hook("claude-code")
        register_hook("claude-code")

    data = json.loads(tmp_settings.read_text())
    assert len(data["hooks"].get("SessionEnd", [])) == 1
    assert len(data["hooks"].get("SessionStart", [])) == 1


def test_register_hook_gemini_installs_only_session_end(tmp_settings, tmp_path):
    """register_hook for gemini must only write SessionEnd (no SessionStart)."""
    with (
        patch("wizard.agent_registration._HOOK_CONFIGS", {
            "gemini": (tmp_settings, "hooks"),
        }),
        patch("wizard.agent_registration._HOOK_SCRIPTS", {
            "gemini": {
                "SessionEnd": tmp_path / "session-end.sh",
            }
        }),
    ):
        result = register_hook("gemini")

    assert result is True
    data = json.loads(tmp_settings.read_text())
    assert "SessionEnd" in data["hooks"]
    assert "SessionStart" not in data["hooks"]


def test_deregister_hook_removes_both_events(tmp_settings, tmp_path):
    """deregister_hook for claude-code must remove both SessionEnd and SessionStart."""
    end_script = tmp_path / "session-end.sh"
    start_script = tmp_path / "session-start.sh"
    hooks_patch = {
        "claude-code": {
            "SessionEnd": end_script,
            "SessionStart": start_script,
        }
    }
    # Pre-populate both events
    tmp_settings.write_text(json.dumps({
        "hooks": {
            "SessionEnd": [{"hooks": [{"type": "command", "command": f"bash {end_script}"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": f"bash {start_script}"}]}],
        }
    }))
    with (
        patch("wizard.agent_registration._HOOK_CONFIGS", {
            "claude-code": (tmp_settings, "hooks"),
        }),
        patch("wizard.agent_registration._HOOK_SCRIPTS", hooks_patch),
    ):
        result = deregister_hook("claude-code")

    assert result is True
    data = json.loads(tmp_settings.read_text())
    assert data["hooks"].get("SessionEnd", []) == []
    assert data["hooks"].get("SessionStart", []) == []


def test_register_hook_unknown_agent_returns_false():
    result = register_hook("unknown-agent")
    assert result is False
