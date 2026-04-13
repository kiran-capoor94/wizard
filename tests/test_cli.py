import json
import sys
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def _fresh_app(wizard_dir: Path):
    """Return a context manager that patches WIZARD_HOME and yields a fresh app."""
    # Ensure the module is not cached so patch triggers a fresh import
    sys.modules.pop("wizard.cli.main", None)

    class _Ctx:
        def __enter__(self):
            self._patcher = patch("wizard.cli.main.WIZARD_HOME", wizard_dir)
            self._patcher.start()
            # Now import — module is freshly loaded with patch applied
            from wizard.cli.main import app

            self.app = app
            return self

        def __exit__(self, *exc):
            self._patcher.stop()

    return _Ctx()


def test_setup_creates_wizard_dir(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    assert result.exit_code == 0
    assert wizard_dir.exists()
    assert (wizard_dir / "config.json").exists()


def test_setup_creates_default_config(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    config = json.loads((wizard_dir / "config.json").read_text())
    assert "jira" in config
    assert "notion" in config
    assert "scrubbing" in config


def test_setup_copies_skills(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    assert result.exit_code == 0
    skills_dir = wizard_dir / "skills"
    assert skills_dir.exists()
    assert (skills_dir / "session-start" / "SKILL.md").exists()
    assert (skills_dir / "task-start" / "SKILL.md").exists()
    assert (skills_dir / "note" / "SKILL.md").exists()
    assert (skills_dir / "meeting" / "SKILL.md").exists()
    assert (skills_dir / "code-review" / "SKILL.md").exists()
    assert (skills_dir / "architecture-debate" / "SKILL.md").exists()
    assert (skills_dir / "session-end" / "SKILL.md").exists()


def test_setup_handles_missing_skills_source(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    fake_skills = tmp_path / "nonexistent_skills"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            with patch("wizard.cli.main._package_skills_dir", return_value=fake_skills):
                result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    assert result.exit_code == 0
    assert not (wizard_dir / "skills").exists()


def test_setup_is_idempotent(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    assert result.exit_code == 0


# --- sync command tests ---

from unittest.mock import MagicMock


def test_sync_calls_sync_all(db_session):
    from tests.helpers import mock_session

    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = []

    with (
        patch("wizard.deps.sync_service", return_value=sync_mock),
        patch("wizard.database.get_session", mock_session(db_session)),
    ):
        from wizard.cli.main import app

        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    sync_mock.sync_all.assert_called_once()


def test_sync_reports_results(db_session):
    from wizard.schemas import SourceSyncStatus
    from tests.helpers import mock_session

    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = [
        SourceSyncStatus(source="jira", ok=True),
        SourceSyncStatus(source="notion_tasks", ok=False, error="timeout"),
    ]

    with (
        patch("wizard.deps.sync_service", return_value=sync_mock),
        patch("wizard.database.get_session", mock_session(db_session)),
    ):
        from wizard.cli.main import app

        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "jira" in result.output.lower()
    assert "notion_tasks" in result.output.lower()
    assert "timeout" in result.output.lower()


# --- doctor command tests ---


def test_doctor_checks_wizard_home(tmp_path):
    import json

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text(json.dumps({"db": ":memory:"}))

    with patch("wizard.cli.main.WIZARD_HOME", wizard_dir):
        from wizard.cli.main import app

        result = runner.invoke(app, ["doctor"])

    assert "config" in result.output.lower()


def test_doctor_reports_missing_wizard_home(tmp_path):
    wizard_dir = tmp_path / ".wizard"  # does not exist

    with patch("wizard.cli.main.WIZARD_HOME", wizard_dir):
        from wizard.cli.main import app

        result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "missing" in result.output.lower()


# --- setup MCP registration tests ---


def test_setup_registers_mcp_in_claude_configs(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    code_cfg = tmp_path / "claude_code_config.json"
    code_cfg.write_text(json.dumps({}))

    from wizard.agent_registration import AgentConfig, _register_json

    patched_agents = {
        "claude-code": AgentConfig(
            agent_id="claude-code",
            config_path=code_cfg,
            format="json",
            mcp_key="mcpServers",
        )
    }

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []

            def _real_register(aid: str) -> None:
                _register_json(patched_agents[aid])

            mock_ar.register.side_effect = _real_register
            mock_ar.write_registered_agents.return_value = None
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    assert result.exit_code == 0
    code_data = json.loads(code_cfg.read_text())
    assert "wizard" in code_data.get("mcpServers", {})
    assert "claude-code" in result.output


def test_setup_skips_mcp_when_config_missing(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    code_cfg = tmp_path / "claude.json"  # does not exist

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    assert result.exit_code == 0
    assert not code_cfg.exists()


# --- uninstall command tests ---


def test_uninstall_removes_wizard_dir_and_mcp(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")
    (wizard_dir / "wizard.db").write_text("")
    skills = wizard_dir / "skills" / "test-skill"
    skills.mkdir(parents=True)

    code_cfg = tmp_path / "claude_code_config.json"
    code_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))

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
        with patch("wizard.mcp_config.agent_registration._AGENTS", patched_agents):
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert not wizard_dir.exists()
    assert "wizard" not in json.loads(code_cfg.read_text()).get("mcpServers", {})


def test_uninstall_nothing_to_do(tmp_path):
    wizard_dir = tmp_path / ".wizard"  # does not exist

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.mcp_config.agent_registration") as mock_ar:
            mock_ar.scan_all_registered.return_value = []
            mock_ar._AGENTS = {}
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert "nothing to uninstall" in result.output.lower()


def test_uninstall_aborts_without_confirmation(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", tmp_path / "nope.json"),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope2.json"),
        ):
            result = runner.invoke(ctx.app, ["uninstall"], input="n\n")

    assert result.exit_code == 0
    assert wizard_dir.exists()  # nothing deleted


def test_uninstall_proceeds_with_confirmation(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", tmp_path / "nope.json"),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope2.json"),
        ):
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
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope.json"),
        ):
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert not wizard_dir.exists()
    # Other MCP entries preserved
    assert json.loads(code_cfg.read_text()) == {"mcpServers": {"other": {}}}


def test_uninstall_is_idempotent(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.mcp_config.agent_registration") as mock_ar:
            mock_ar.scan_all_registered.return_value = []
            mock_ar._AGENTS = {}
            runner.invoke(ctx.app, ["uninstall", "--yes"])
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert "nothing to uninstall" in result.output.lower()


# --- setup --agent flag tests ---


def test_setup_agent_flag_registers_gemini(tmp_path):
    from unittest.mock import MagicMock

    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "gemini"])

    mock_ar.register.assert_called_with("gemini")
    mock_ar.write_registered_agents.assert_called()
    assert result.exit_code == 0


def test_setup_agent_all_registers_all_five(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "all"])

    registered_ids = [call.args[0] for call in mock_ar.register.call_args_list]
    assert set(registered_ids) == {"claude-code", "claude-desktop", "gemini", "opencode", "codex"}
    assert result.exit_code == 0


def test_setup_writes_registered_agents_json(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"])

    mock_ar.write_registered_agents.assert_called_once_with(["claude-code"])
    assert result.exit_code == 0


def test_setup_unknown_agent_exits_nonzero(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "notarealbot"])

    assert result.exit_code != 0


def test_setup_interactive_prompt_selects_agent(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            # "3" selects "gemini" (1=claude-code, 2=claude-desktop, 3=gemini, ...)
            result = runner.invoke(ctx.app, ["setup"], input="3\n")

    mock_ar.register.assert_called_with("gemini")
    assert result.exit_code == 0


def test_setup_interactive_prompt_invalid_selection(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup"], input="99\n")

    assert result.exit_code != 0
