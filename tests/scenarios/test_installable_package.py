from unittest.mock import patch

from wizard.agent_registration import _json_entry, _opencode_entry, _toml_entry, refresh_hooks


def test_json_entry_uses_wizard_server():
    entry = _json_entry()
    assert entry["command"] == "wizard-server"
    assert entry["args"] == []
    assert entry["type"] == "stdio"


def test_opencode_entry_uses_wizard_server():
    entry = _opencode_entry()
    assert entry["command"] == ["wizard-server"]
    assert entry["type"] == "local"


def test_toml_entry_uses_wizard_server():
    entry = _toml_entry()
    assert entry["command"] == "wizard-server"
    assert entry["args"] == []


def test_refresh_hooks_copies_scripts_to_wizard_dir(tmp_path):
    hooks_dest = tmp_path / "hooks"
    hooks_dest.mkdir()
    with patch("wizard.agent_registration._WIZARD_HOOKS_DIR", hooks_dest):
        refresh_hooks()
    assert (hooks_dest / "session-end.sh").exists()
    assert (hooks_dest / "session-start.sh").exists()
    assert (hooks_dest / "session-start-minimal.sh").exists()
