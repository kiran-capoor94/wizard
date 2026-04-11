import json
from unittest.mock import patch

from wizard.mcp_config import get_mcp_server_entry, register_wizard_mcp


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
