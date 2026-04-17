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


def test_setup_creates_wizard_dir(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code == 0
    assert wizard_dir.exists()
    assert (wizard_dir / "config.json").exists()


def test_setup_creates_default_config(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    config = json.loads((wizard_dir / "config.json").read_text())
    assert "jira" in config
    assert "notion" in config
    assert "scrubbing" in config


def test_setup_copies_skills(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

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
                result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code == 0
    assert not (wizard_dir / "skills").exists()


def test_setup_is_idempotent(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code == 0


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
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

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
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code == 0
    assert not code_cfg.exists()


def test_setup_agent_flag_registers_gemini(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "gemini"], input="4\n")

    mock_ar.register.assert_called_with("gemini")
    mock_ar.write_registered_agents.assert_called()
    assert result.exit_code == 0


def test_setup_agent_all_registers_all_five(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "all"], input="4\n")

    registered_ids = [call.args[0] for call in mock_ar.register.call_args_list]
    assert set(registered_ids) == {"claude-code", "claude-desktop", "gemini", "opencode", "codex"}
    assert result.exit_code == 0


def test_setup_writes_registered_agents_json(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    mock_ar.write_registered_agents.assert_called_once_with(["claude-code"])
    assert result.exit_code == 0


def test_setup_unknown_agent_exits_nonzero(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "notarealbot"], input="4\n")

    assert result.exit_code != 0


def test_setup_interactive_prompt_selects_agent(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            # "4" selects "Neither" for integration; "3" selects "gemini"
            result = runner.invoke(ctx.app, ["setup"], input="4\n3\n")

    mock_ar.register.assert_called_with("gemini")
    assert result.exit_code == 0


def test_setup_interactive_prompt_invalid_selection(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup"], input="4\n99\n")

    assert result.exit_code != 0


def test_setup_asks_which_integrations(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")
    assert result.exit_code == 0
    assert "integration" in result.output.lower()


def test_setup_integration_invalid_selection_exits(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="9\n")
    assert result.exit_code != 0


def test_setup_runs_migrations_when_db_missing(tmp_path):
    """setup() should call alembic upgrade head when DB is absent."""
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._db_is_healthy", return_value=False), \
             patch("wizard.cli.main._run_update_step", return_value=(True, "")) as mock_step:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code == 0
    calls = [call for call in mock_step.call_args_list
              if "alembic" in str(call)]
    assert len(calls) == 1


def test_setup_skips_migrations_when_db_healthy(tmp_path):
    """setup() should NOT call alembic upgrade head when DB already has all tables."""
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._db_is_healthy", return_value=True), \
             patch("wizard.cli.main._run_update_step", return_value=(True, "")) as mock_step:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code == 0
    alembic_calls = [call for call in mock_step.call_args_list
                     if "alembic" in str(call)]
    assert len(alembic_calls) == 0


def test_setup_exits_nonzero_when_migrations_fail(tmp_path):
    """setup() should exit with code 1 when alembic upgrade head fails."""
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._db_is_healthy", return_value=False), \
             patch("wizard.cli.main._run_update_step", return_value=(False, "alembic error output")):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")

    assert result.exit_code != 0
