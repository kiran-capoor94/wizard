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


# --- sync command tests ---

from unittest.mock import MagicMock


def test_sync_calls_sync_all(db_session):
    from tests.helpers import mock_session

    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = []

    with (
        patch("wizard.deps.get_sync_service", return_value=sync_mock),
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
        patch("wizard.deps.get_sync_service", return_value=sync_mock),
        patch("wizard.database.get_session", mock_session(db_session)),
    ):
        from wizard.cli.main import app

        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "jira" in result.output.lower()
    assert "notion_tasks" in result.output.lower()
    assert "timeout" in result.output.lower()


# --- doctor command tests ---


def test_doctor_checks_wizard_home(tmp_path, monkeypatch):
    import json

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    db_path = wizard_dir / "wizard.db"
    db_path.touch()
    (wizard_dir / "config.json").write_text(json.dumps({}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(wizard_dir / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(db_path))

    with patch("wizard.cli.main.WIZARD_HOME", wizard_dir):
        from wizard.cli.main import app

        result = runner.invoke(app, ["doctor"])

    # Check 1 (db file) passes; check 2 (notion token) fails → output contains check name
    assert "db" in result.output.lower() or "notion" in result.output.lower()


def test_doctor_reports_missing_wizard_home(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DB", str(tmp_path / "no_such.db"))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "nonexistent_config.json"))

    from wizard.cli.main import app

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "missing" in result.output.lower() or "fail" in result.output.lower()


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


# --- setup --agent flag tests ---


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


# --- configure --notion tests ---


def test_configure_notion_runs_discovery(tmp_path):
    from unittest.mock import patch
    import json
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    config = {
        "notion": {
            "token": "test-token",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (wizard_dir / "config.json").write_text(json.dumps(config))

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.notion_discovery") as mock_nd, \
             patch("wizard.cli.main.NotionSdkClient"):
            mock_nd.fetch_db_properties.return_value = {"Task": "title", "Status": "status"}
            mock_nd.match_properties.return_value = {
                "task_name": "Task", "task_status": "Status",
                "task_priority": None, "task_due_date": None,
                "task_jira_key": None, "meeting_title": "Meeting name",
                "meeting_date": None, "meeting_url": None, "meeting_summary": None,
            }
            result = runner.invoke(ctx.app, ["configure", "--notion"])

    mock_nd.fetch_db_properties.assert_called()
    mock_nd.match_properties.assert_called()
    assert result.exit_code == 0


# --- doctor command tests (new 10-check implementation) ---


def test_doctor_check_1_db_file_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(tmp_path / "no_such.db"))
    from typer.testing import CliRunner
    from wizard.cli.main import app
    runner_local = CliRunner()
    result = runner_local.invoke(app, ["doctor"])
    assert result.exit_code != 0
    assert "database" in result.output.lower() or "db" in result.output.lower()


def test_doctor_all_checks_pass_with_valid_setup(tmp_path, monkeypatch):
    import json
    from unittest.mock import patch
    db_path = tmp_path / "wizard.db"
    db_path.touch()
    config = {
        "notion": {"token": "tok", "tasks_ds_id": "t", "meetings_ds_id": "m"},
        "jira": {"token": "jtok", "base_url": "https://jira.example.com", "project_key": "ENG"},
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(db_path))
    with patch("wizard.cli.doctor._check_db_tables", return_value=(True, "ok")), \
         patch("wizard.cli.doctor._check_migration_current", return_value=(True, "ok")), \
         patch("wizard.cli.doctor._check_agent_registrations", return_value=(True, "ok")), \
         patch("wizard.cli.doctor._check_allowlist_file", return_value=(True, "ok")), \
         patch("wizard.cli.doctor._check_skills_installed", return_value=(True, "ok")), \
         patch("wizard.cli.doctor._check_notion_schema", return_value=(True, "Notion schema matches live DB")):
        from typer.testing import CliRunner
        from wizard.cli.main import app
        runner_local = CliRunner()
        result = runner_local.invoke(app, ["doctor", "--all"])
    assert result.exit_code == 0


def test_doctor_stops_at_first_failure_without_all_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(tmp_path / "no_such.db"))
    from typer.testing import CliRunner
    from wizard.cli.main import app
    runner_local = CliRunner()
    result = runner_local.invoke(app, ["doctor"])
    assert result.exit_code != 0


# --- _check_notion_schema unit tests ---


def test_check_notion_schema_passes_when_live_db_matches(tmp_path, monkeypatch):
    """_check_notion_schema returns True when all expected properties exist with correct types."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        "Task": "title",
        "Status": "status",
        "Priority": "select",
        "Due date": "date",
        "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is True
    assert "matches" in msg


def test_check_notion_schema_fails_when_task_property_missing(tmp_path, monkeypatch):
    """_check_notion_schema returns False when a tasks DB property is absent."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        # "Task" title property is missing
        "Status": "status",
        "Priority": "select",
        "Due date": "date",
        "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is False
    assert "Tasks DB" in msg
    assert "'Task'" in msg


def test_check_notion_schema_fails_when_property_has_wrong_type(tmp_path, monkeypatch):
    """_check_notion_schema returns False when a property exists but has the wrong type."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        "Task": "title",
        "Status": "status",
        "Priority": "multi_select",  # wrong — should be "select"
        "Due date": "date",
        "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is False
    assert "Tasks DB" in msg
    assert "multi_select" in msg
    assert "select" in msg


def test_check_notion_schema_fails_when_token_not_configured(tmp_path, monkeypatch):
    """_check_notion_schema returns False immediately when Notion token is empty."""
    import json
    config = {
        "notion": {
            "token": "",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    with patch("wizard.integrations.NotionSdkClient") as mock_client:
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    mock_client.assert_not_called()
    assert ok is False
    assert "configured" in msg


def test_check_notion_schema_fails_on_connectivity_error(tmp_path, monkeypatch):
    """_check_notion_schema returns a connectivity error when fetch_db_properties returns {} for both DBs."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    with patch("wizard.notion_discovery.fetch_db_properties", return_value={}), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is False
    assert "Notion API" in msg or "network" in msg.lower() or "token" in msg.lower()


def test_check_notion_schema_fails_when_one_db_unreachable(tmp_path, monkeypatch):
    """When only tasks DB is unreachable, all task fields are reported missing; meetings pass."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[{}, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is False
    assert "Tasks DB" in msg
    assert "Meetings DB" not in msg


def test_check_db_tables_fails_when_task_state_missing(tmp_path, monkeypatch):
    """_check_db_tables must flag a DB that is missing the task_state table."""
    import sqlite3
    db_path = tmp_path / "wizard.db"
    conn = sqlite3.connect(str(db_path))
    for table in ["task", "note", "meeting", "wizardsession", "toolcall"]:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("WIZARD_DB", str(db_path))
    from wizard.cli.doctor import _check_db_tables
    ok, msg = _check_db_tables()
    assert ok is False
    assert "task_state" in msg


def test_check_notion_schema_uses_schema_meeting_category_field(tmp_path, monkeypatch):
    """schema.meeting_category is used — not the hardcoded string 'Category'."""
    import json
    from unittest.mock import patch
    config = {
        "notion": {
            "token": "tok",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
            "notion_schema": {"meeting_category": "Meeting Type"},
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        "Task": "title", "Status": "status",
        "Priority": "select", "Due date": "date", "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title", "Date": "date",
        "Krisp URL": "url", "Summary": "rich_text",
        "Meeting Type": "multi_select",  # custom name, not "Category"
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.doctor import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is True, f"Expected pass but got: {msg}"


def test_db_is_healthy_returns_false_when_file_missing(tmp_path):
    from wizard.cli.doctor import _db_is_healthy
    assert _db_is_healthy(tmp_path / "no_such.db") is False


def test_db_is_healthy_returns_false_when_tables_missing(tmp_path):
    import sqlite3
    from wizard.cli.doctor import _db_is_healthy
    db = tmp_path / "wizard.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE task (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    assert _db_is_healthy(db) is False


def test_db_is_healthy_returns_true_when_all_tables_present(tmp_path):
    import sqlite3
    from wizard.cli.doctor import _db_is_healthy
    db = tmp_path / "wizard.db"
    conn = sqlite3.connect(str(db))
    for t in ["task", "note", "meeting", "wizardsession", "toolcall", "task_state"]:
        conn.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    assert _db_is_healthy(db) is True


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
