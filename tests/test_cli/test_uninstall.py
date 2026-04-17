import json
import sys
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def _fresh_app(wizard_dir: Path):
    """Return a context manager that patches WIZARD_HOME and yields a fresh app."""
    sys.modules.pop("wizard.cli.main", None)

    class _Ctx:
        def __enter__(self):
            self._patcher = patch("wizard.cli.main.WIZARD_HOME", wizard_dir)
            self._patcher.start()
            from wizard.cli.main import app

            self.app = app
            return self

        def __exit__(self, *exc):
            self._patcher.stop()

    return _Ctx()


def test_uninstall_removes_wizard_dir_and_mcp(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")
    (wizard_dir / "wizard.db").write_text("")
    skills = wizard_dir / "skills" / "test-skill"
    skills.mkdir(parents=True)

    code_cfg = tmp_path / "claude_code_config.json"
    code_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))

    import wizard.agent_registration as ar
    from wizard.agent_registration import AgentConfig

    patched_agents = {
        "claude-code": AgentConfig(
            agent_id="claude-code",
            config_path=code_cfg,
            format="json",
            mcp_key="mcpServers",
        )
    }

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch.object(ar, "read_registered_agents", return_value=["claude-code"]),
            patch.object(ar, "_AGENTS", patched_agents),
        ):
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert not wizard_dir.exists()
    assert "wizard" not in json.loads(code_cfg.read_text()).get("mcpServers", {})


def test_uninstall_nothing_to_do(tmp_path):
    wizard_dir = tmp_path / ".wizard"  # does not exist

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            mock_ar.scan_all_registered.return_value = []
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert "nothing to uninstall" in result.output.lower()


def test_uninstall_aborts_without_confirmation(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            mock_ar.scan_all_registered.return_value = []
            result = runner.invoke(ctx.app, ["uninstall"], input="n\n")

    assert result.exit_code == 0
    assert wizard_dir.exists()  # nothing deleted


def test_uninstall_proceeds_with_confirmation(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            mock_ar.scan_all_registered.return_value = []
            result = runner.invoke(ctx.app, ["uninstall"], input="y\n")

    assert result.exit_code == 0
    assert not wizard_dir.exists()


def test_uninstall_partial_state(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")
    # No wizard.db, no skills, no MCP registrations

    code_cfg = tmp_path / "claude.json"
    code_cfg.write_text(json.dumps({"mcpServers": {"other": {}}}))  # no wizard entry

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            mock_ar.scan_all_registered.return_value = []
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert not wizard_dir.exists()
    # Other MCP entries preserved (unaffected since no agents deregistered)
    assert json.loads(code_cfg.read_text()) == {"mcpServers": {"other": {}}}


def test_uninstall_is_idempotent(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            mock_ar.scan_all_registered.return_value = []
            runner.invoke(ctx.app, ["uninstall", "--yes"])
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert "nothing to uninstall" in result.output.lower()


def test_uninstall_reads_registered_agents_and_deregisters(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = ["claude-code", "gemini"]
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    deregistered = [call.args[0] for call in mock_ar.deregister.call_args_list]
    assert "claude-code" in deregistered
    assert "gemini" in deregistered
    assert result.exit_code == 0


def test_uninstall_falls_back_to_scan_if_no_registered_agents_file(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            mock_ar.scan_all_registered.return_value = ["claude-desktop"]
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    mock_ar.scan_all_registered.assert_called_once()
    mock_ar.deregister.assert_called_with("claude-desktop")
    assert result.exit_code == 0
