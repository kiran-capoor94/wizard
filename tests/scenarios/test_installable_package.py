from unittest.mock import MagicMock, patch

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


def test_run_migrations_is_callable():
    """run_migrations() must be importable and callable (no import errors)."""
    from wizard.database import run_migrations
    assert callable(run_migrations)


def test_is_editable_install_returns_bool():
    from wizard.cli.main import is_editable_install
    result = is_editable_install()
    assert isinstance(result, bool)


def test_is_editable_install_true_when_editable():
    """Returns True when direct_url.json contains editable=true."""
    from wizard.cli.main import is_editable_install

    fake_meta = MagicMock()
    fake_meta.read_text.return_value = '{"url": "file:///repo", "dir_info": {"editable": true}}'
    with patch("wizard.cli.main.importlib_metadata.distribution", return_value=fake_meta):
        assert is_editable_install() is True


def test_is_editable_install_false_when_tool_install():
    """Returns False when direct_url.json has no editable flag (uv tool install)."""
    from wizard.cli.main import is_editable_install

    fake_meta = MagicMock()
    fake_meta.read_text.return_value = '{"url": "https://github.com/...", "vcs_info": {}}'
    with patch("wizard.cli.main.importlib_metadata.distribution", return_value=fake_meta):
        assert is_editable_install() is False
