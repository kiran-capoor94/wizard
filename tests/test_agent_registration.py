import json
import sys
from pathlib import Path
from unittest.mock import patch


def _make_json_config(agent_id: str, config_path: Path, mcp_key: str = "mcpServers"):
    """Helper: build an AgentConfig pointing to a tmp path."""
    from wizard.agent_registration import AgentConfig
    return AgentConfig(
        agent_id=agent_id,
        config_path=config_path,
        format="json",
        mcp_key=mcp_key,
    )


def _make_toml_config(agent_id: str, config_path: Path, mcp_key: str = "mcpServers"):
    from wizard.agent_registration import AgentConfig
    return AgentConfig(
        agent_id=agent_id,
        config_path=config_path,
        format="toml",
        mcp_key=mcp_key,
    )


def test_register_creates_config_file(tmp_path):
    config_path = tmp_path / "claude.json"
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import register
        register("claude-code")
    data = json.loads(config_path.read_text())
    assert "mcpServers" in data
    assert "wizard" in data["mcpServers"]


def test_register_is_idempotent(tmp_path):
    config_path = tmp_path / "claude.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "other-tool": {"command": "other"},
            "wizard": {"command": "old"},
        }
    }))
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import register
        register("claude-code")
    data = json.loads(config_path.read_text())
    assert "other-tool" in data["mcpServers"]
    assert isinstance(data["mcpServers"]["wizard"], dict)
    assert data["mcpServers"]["wizard"]["command"] == "uv"


def test_register_creates_parent_dirs(tmp_path):
    config_path = tmp_path / "deep" / "nested" / "config.json"
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import register
        register("claude-code")
    assert config_path.exists()


def test_register_raises_on_malformed_json(tmp_path):
    import pytest
    config_path = tmp_path / "bad.json"
    config_path.write_text("not valid json {{{")
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import register
        from wizard.integrations import ConfigurationError
        with pytest.raises(ConfigurationError):
            register("claude-code")


def test_deregister_removes_wizard_key(tmp_path):
    config_path = tmp_path / "claude.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "other": {"command": "other"},
            "wizard": {"command": "uv"},
        }
    }))
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import deregister
        deregister("claude-code")
    data = json.loads(config_path.read_text())
    assert "wizard" not in data["mcpServers"]
    assert "other" in data["mcpServers"]


def test_deregister_noop_if_file_absent(tmp_path):
    config_path = tmp_path / "nonexistent.json"
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import deregister
        deregister("claude-code")  # must not raise


def test_deregister_unknown_agent_is_noop():
    from wizard.agent_registration import deregister
    deregister("does-not-exist")  # must not raise


def test_register_unknown_agent_raises():
    import pytest
    from wizard.agent_registration import register
    from wizard.integrations import ConfigurationError
    with pytest.raises(ConfigurationError, match="Unknown agent"):
        register("does-not-exist")


def test_register_opencode_uses_local_type(tmp_path):
    config_path = tmp_path / "opencode.json"
    cfg = _make_json_config("opencode", config_path, mcp_key="mcp")
    with patch("wizard.agent_registration._AGENTS", {"opencode": cfg}):
        from wizard.agent_registration import register
        register("opencode")
    data = json.loads(config_path.read_text())
    assert "mcp" in data
    assert "wizard" in data["mcp"]
    assert data["mcp"]["wizard"]["type"] == "local"
    assert isinstance(data["mcp"]["wizard"]["command"], list)
    assert data["mcp"]["wizard"]["enabled"] is True


def test_register_codex_toml(tmp_path):
    import tomllib
    config_path = tmp_path / "codex.toml"
    cfg = _make_toml_config("codex", config_path)
    with patch("wizard.agent_registration._AGENTS", {"codex": cfg}):
        from wizard.agent_registration import register
        register("codex")
    data = tomllib.loads(config_path.read_text())
    assert "mcpServers" in data
    assert "wizard" in data["mcpServers"]
    assert data["mcpServers"]["wizard"]["command"] == "uv"


def test_register_codex_toml_idempotent(tmp_path):
    import tomllib
    import tomli_w
    config_path = tmp_path / "codex.toml"
    existing = {"mcpServers": {"other": {"command": "other"}}, "other_section": {"key": "val"}}
    config_path.write_bytes(tomli_w.dumps(existing).encode())
    cfg = _make_toml_config("codex", config_path)
    with patch("wizard.agent_registration._AGENTS", {"codex": cfg}):
        from wizard.agent_registration import register
        register("codex")
    data = tomllib.loads(config_path.read_text())
    assert "other" in data["mcpServers"]
    assert "wizard" in data["mcpServers"]
    assert data.get("other_section", {}).get("key") == "val"


def test_deregister_codex_toml(tmp_path):
    import tomllib
    import tomli_w
    config_path = tmp_path / "codex.toml"
    existing = {"mcpServers": {"other": {"command": "other"}, "wizard": {"command": "uv"}}}
    config_path.write_bytes(tomli_w.dumps(existing).encode())
    cfg = _make_toml_config("codex", config_path)
    with patch("wizard.agent_registration._AGENTS", {"codex": cfg}):
        from wizard.agent_registration import deregister
        deregister("codex")
    data = tomllib.loads(config_path.read_text())
    assert "wizard" not in data["mcpServers"]
    assert "other" in data["mcpServers"]


def test_deregister_toml_noop_if_absent(tmp_path):
    config_path = tmp_path / "no_such.toml"
    cfg = _make_toml_config("codex", config_path)
    with patch("wizard.agent_registration._AGENTS", {"codex": cfg}):
        from wizard.agent_registration import deregister
        deregister("codex")  # must not raise


def test_read_registered_agents_absent(tmp_path):
    reg_path = tmp_path / "registered_agents.json"
    with patch("wizard.agent_registration._REGISTERED_AGENTS_PATH", reg_path):
        from wizard.agent_registration import read_registered_agents
        assert read_registered_agents() == []


def test_read_write_registered_agents(tmp_path):
    reg_path = tmp_path / "registered_agents.json"
    with patch("wizard.agent_registration._REGISTERED_AGENTS_PATH", reg_path):
        from wizard.agent_registration import read_registered_agents, write_registered_agents
        write_registered_agents(["claude-code", "gemini"])
        assert read_registered_agents() == ["claude-code", "gemini"]


def test_read_registered_agents_malformed_returns_empty(tmp_path):
    reg_path = tmp_path / "registered_agents.json"
    reg_path.write_text("not valid json{{{")
    with patch("wizard.agent_registration._REGISTERED_AGENTS_PATH", reg_path):
        from wizard.agent_registration import read_registered_agents
        assert read_registered_agents() == []


def test_scan_all_registered_finds_json_agent(tmp_path):
    config_path = tmp_path / "claude.json"
    config_path.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import scan_all_registered
        found = scan_all_registered()
    assert "claude-code" in found


def test_scan_all_registered_skips_absent_file(tmp_path):
    config_path = tmp_path / "no_such.json"
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import scan_all_registered
        found = scan_all_registered()
    assert "claude-code" not in found


def test_scan_all_registered_ignores_malformed(tmp_path):
    config_path = tmp_path / "bad.json"
    config_path.write_text("not json")
    cfg = _make_json_config("claude-code", config_path)
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import scan_all_registered
        found = scan_all_registered()  # must not raise
    assert "claude-code" not in found


def test_deregister_raises_on_malformed_json(tmp_path):
    import pytest
    config_path = tmp_path / "bad.json"
    config_path.write_text("not valid json {{{")
    from wizard.agent_registration import AgentConfig
    cfg = AgentConfig(
        agent_id="claude-code",
        config_path=config_path,
        format="json",
        mcp_key="mcpServers",
    )
    with patch("wizard.agent_registration._AGENTS", {"claude-code": cfg}):
        from wizard.agent_registration import deregister
        from wizard.integrations import ConfigurationError
        with pytest.raises(ConfigurationError):
            deregister("claude-code")


def test_deregister_raises_on_malformed_toml(tmp_path):
    import pytest
    config_path = tmp_path / "bad.toml"
    config_path.write_text("not valid toml {{{")
    from wizard.agent_registration import AgentConfig
    cfg = AgentConfig(
        agent_id="codex",
        config_path=config_path,
        format="toml",
        mcp_key="mcpServers",
    )
    with patch("wizard.agent_registration._AGENTS", {"codex": cfg}):
        from wizard.agent_registration import deregister
        from wizard.integrations import ConfigurationError
        with pytest.raises(ConfigurationError):
            deregister("codex")
