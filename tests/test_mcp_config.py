from pathlib import Path
from unittest.mock import patch

from wizard.mcp_config import (
    CLAUDE_CODE_CONFIG,
    CLAUDE_DESKTOP_CONFIG,
    deregister_wizard_mcp,
    find_wizard_mcp_targets,
    get_mcp_server_entry,
    register_wizard_mcp,
)


def test_get_mcp_server_entry_returns_uv_command():
    entry = get_mcp_server_entry()
    assert entry["command"] == "uv"
    assert "--directory" in entry["args"]
    assert "server.py" in entry["args"]


def test_claude_code_config_constant_is_path():
    assert isinstance(CLAUDE_CODE_CONFIG, Path)
    assert "claude" in str(CLAUDE_CODE_CONFIG).lower()


def test_claude_desktop_config_constant_is_path():
    assert isinstance(CLAUDE_DESKTOP_CONFIG, Path)
    assert "claude" in str(CLAUDE_DESKTOP_CONFIG).lower()


def test_register_wizard_mcp_delegates_to_agent_registration():
    with patch("wizard.mcp_config.agent_registration") as mock_ar:
        register_wizard_mcp()
    mock_ar.register.assert_called_once_with("claude-code")


def test_deregister_wizard_mcp_delegates_to_agent_registration():
    with patch("wizard.mcp_config.agent_registration") as mock_ar:
        deregister_wizard_mcp()
    mock_ar.deregister.assert_called_once_with("claude-code")


def test_register_wizard_mcp_returns_none():
    with patch("wizard.mcp_config.agent_registration"):
        result = register_wizard_mcp()
    assert result is None


def test_deregister_wizard_mcp_returns_none():
    with patch("wizard.mcp_config.agent_registration"):
        result = deregister_wizard_mcp()
    assert result is None


def test_find_wizard_mcp_targets_delegates_to_scan(tmp_path):
    config_path = tmp_path / "claude.json"
    with patch("wizard.mcp_config.agent_registration") as mock_ar:
        from wizard.agent_registration import AgentConfig
        mock_ar.scan_all_registered.return_value = ["claude-code"]
        mock_ar._AGENTS = {
            "claude-code": AgentConfig(
                agent_id="claude-code",
                config_path=config_path,
                format="json",
                mcp_key="mcpServers",
            )
        }
        result = find_wizard_mcp_targets()
    assert config_path in result


def test_find_wizard_mcp_targets_returns_empty_when_none_registered():
    with patch("wizard.mcp_config.agent_registration") as mock_ar:
        mock_ar.scan_all_registered.return_value = []
        mock_ar._AGENTS = {}
        result = find_wizard_mcp_targets()
    assert result == []


def test_register_wizard_mcp_calls_through_each_invocation():
    """Each call to register_wizard_mcp delegates to agent_registration.register."""
    with patch("wizard.mcp_config.agent_registration") as mock_ar:
        register_wizard_mcp()
        register_wizard_mcp()
    assert mock_ar.register.call_count == 2
    mock_ar.register.assert_called_with("claude-code")


def test_get_mcp_entry_matches_agent_registration_json_entry():
    """get_mcp_server_entry() must return the same shape as agent_registration._json_entry()."""
    from wizard.agent_registration import _json_entry
    assert get_mcp_server_entry() == _json_entry()
