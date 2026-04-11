import json
from unittest.mock import patch

from wizard.mcp_config import (
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


def _patch_config_paths(tmp_path):
    """Return a context-manager that redirects both config constants to temp files."""
    code_cfg = tmp_path / "claude.json"
    desktop_cfg = tmp_path / "claude_desktop_config.json"
    return (
        code_cfg,
        desktop_cfg,
        patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
        patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", desktop_cfg),
    )


def test_register_into_existing_config(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"someKey": True}))
    desktop_cfg.write_text(json.dumps({"preferences": {}}))

    with p1, p2:
        results = register_wizard_mcp()

    code_data = json.loads(code_cfg.read_text())
    assert "wizard" in code_data["mcpServers"]
    assert code_data["someKey"] is True  # existing keys preserved

    desktop_data = json.loads(desktop_cfg.read_text())
    assert "wizard" in desktop_data["mcpServers"]
    assert desktop_data["preferences"] == {}  # existing keys preserved

    assert len(results) == 2


def test_register_is_idempotent(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({}))
    desktop_cfg.write_text(json.dumps({}))

    with p1, p2:
        register_wizard_mcp()
        first = json.loads(code_cfg.read_text())
        register_wizard_mcp()
        second = json.loads(code_cfg.read_text())

    assert first == second


def test_register_skips_missing_file(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    # Neither file exists

    with p1, p2:
        results = register_wizard_mcp()

    assert len(results) == 0


def test_register_skips_invalid_json(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text("not json{{{")

    with p1, p2:
        results = register_wizard_mcp()

    assert len(results) == 0
    # File must not be corrupted
    assert code_cfg.read_text() == "not json{{{"


def test_find_targets_returns_names_with_wizard_entry(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"mcpServers": {"wizard": {}}}))
    desktop_cfg.write_text(json.dumps({"mcpServers": {"other": {}}}))

    with p1, p2:
        results = find_wizard_mcp_targets()

    assert results == ["Claude Code"]


def test_find_targets_skips_missing_and_invalid(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text("broken{")
    # desktop_cfg doesn't exist

    with p1, p2:
        results = find_wizard_mcp_targets()

    assert results == []


def test_deregister_removes_wizard_entry(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}, "other": {}}}))
    desktop_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))

    with p1, p2:
        results = deregister_wizard_mcp()

    code_data = json.loads(code_cfg.read_text())
    assert "wizard" not in code_data["mcpServers"]
    assert "other" in code_data["mcpServers"]

    desktop_data = json.loads(desktop_cfg.read_text())
    assert "mcpServers" not in desktop_data  # empty mcpServers removed

    assert len(results) == 2


def test_deregister_noop_when_no_wizard_entry(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"mcpServers": {"other": {}}}))

    with p1, p2:
        results = deregister_wizard_mcp()

    assert len(results) == 0
    # File unchanged
    assert json.loads(code_cfg.read_text()) == {"mcpServers": {"other": {}}}


def test_deregister_skips_missing_file(tmp_path):
    _code_cfg, _desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)

    with p1, p2:
        results = deregister_wizard_mcp()

    assert len(results) == 0


def test_deregister_skips_invalid_json(tmp_path):
    code_cfg, _desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text("broken}")

    with p1, p2:
        results = deregister_wizard_mcp()

    assert len(results) == 0
    assert code_cfg.read_text() == "broken}"
