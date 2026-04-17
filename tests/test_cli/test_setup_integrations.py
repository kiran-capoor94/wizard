import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
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


def test_setup_notion_collects_token_and_ids(tmp_path):
    """Selecting Notion (1) prompts for token, daily page ID, tasks URL, meetings URL; resolves ds IDs."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery"), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\nmy-page-id\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["token"] == "my-token"
    assert cfg["notion"]["daily_page_parent_id"] == "my-page-id"
    assert cfg["notion"]["tasks_ds_id"] == "tasks-ds-id"
    assert cfg["notion"]["meetings_ds_id"] == "meetings-ds-id"


def test_setup_notion_runs_discovery(tmp_path):
    """After collecting Notion credentials, setup calls _run_notion_discovery."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery") as mock_disc, \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    mock_disc.assert_called_once()


def test_setup_notion_optional_daily_page_id_can_be_skipped(tmp_path):
    """Pressing Enter on daily page ID prompt skips it (leaves field empty)."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery"), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["daily_page_parent_id"] == ""


def test_setup_jira_collects_all_fields(tmp_path):
    """Selecting Jira (2) prompts for base_url, project_key, email, token."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="2\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-api-token\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["jira"]["base_url"] == "https://acme.atlassian.net"
    assert cfg["jira"]["project_key"] == "ENG"
    assert cfg["jira"]["email"] == "dev@acme.com"
    assert cfg["jira"]["token"] == "jira-api-token"


def test_setup_both_configures_notion_and_jira(tmp_path):
    """Selecting Both (3) runs both _configure_notion and _configure_jira."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery"), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="3\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["token"] == "my-token"
    assert cfg["jira"]["token"] == "jira-token"


def test_setup_skips_notion_when_already_configured(tmp_path):
    """If Notion token + DB IDs are already set, skip prompts and print hint."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    cfg = {
        "notion": {
            "token": "existing-token",
            "tasks_ds_id": "existing-tasks",
            "meetings_ds_id": "existing-meetings",
            "daily_page_parent_id": "",
        },
        "jira": {"base_url": "", "project_key": "", "token": "", "email": ""},
        "scrubbing": {"enabled": True, "allowlist": []},
    }
    (wizard_dir / "config.json").write_text(json.dumps(cfg))

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery") as mock_disc:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="1\n")

    assert result.exit_code == 0
    mock_disc.assert_not_called()
    assert "already configured" in result.output.lower()
    assert "wizard configure --notion" in result.output


def test_setup_skips_jira_when_already_configured(tmp_path):
    """If all Jira fields are set, skip prompts and print hint."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    cfg = {
        "notion": {"token": "", "tasks_ds_id": "", "meetings_ds_id": "", "daily_page_parent_id": ""},
        "jira": {
            "base_url": "https://acme.atlassian.net",
            "project_key": "ENG",
            "token": "existing-token",
            "email": "dev@acme.com",
        },
        "scrubbing": {"enabled": True, "allowlist": []},
    }
    (wizard_dir / "config.json").write_text(json.dumps(cfg))

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="2\n")

    assert result.exit_code == 0
    assert "already configured" in result.output.lower()
    assert "wizard configure --jira" in result.output


def test_setup_final_summary_shows_configured_integrations(tmp_path):
    """Final summary lists Notion as configured and Jira as skipped."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery"), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    assert result.exit_code == 0
    assert "notion" in result.output.lower()
    assert "configured" in result.output.lower()
    assert "jira" in result.output.lower()
    assert "wizard configure --jira" in result.output


def test_setup_both_does_not_clobber_notion_schema(tmp_path):
    """When Both is selected, Jira write must not discard notion_schema written by discovery."""
    wizard_dir = tmp_path / ".wizard"

    def fake_discovery(config_path):
        with open(config_path) as f:
            cfg = json.load(f)
        cfg.setdefault("notion", {})["notion_schema"] = {"task_name": "Task"}
        with open(config_path, "w") as f:
            json.dump(cfg, f, indent=2)

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery", side_effect=fake_discovery), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="3\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
            )

    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg.get("notion", {}).get("notion_schema") == {"task_name": "Task"}
    assert cfg["jira"]["token"] == "jira-token"


def test_setup_notion_configuration_error_exits_cleanly(tmp_path):
    """If Notion schema discovery raises ConfigurationError, setup exits with code 1 and a clean message."""
    from wizard.integrations import ConfigurationError
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery", side_effect=ConfigurationError("task_name required")), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    assert result.exit_code != 0
    assert "notion configuration failed" in result.output.lower() or "notion configuration failed" in (result.stderr or "").lower()


def test_setup_notion_retries_on_api_error(tmp_path):
    """If data_sources.retrieve fails (bad token, 404, network), setup re-prompts."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery"), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=[
                 httpx.HTTPError("404 Not Found"),  # first tasks attempt fails
                 "tasks-ds-id",                        # second tasks attempt succeeds
                 "meetings-ds-id",
             ]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input=(
                    "1\nmy-token\n\n"
                    "https://notion.so/workspace/Tasks-abc123def456789012345678901234ab\n"
                    "https://notion.so/workspace/Tasks-abc123def456789012345678901234ab\n"
                    "https://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n"
                ),
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["tasks_ds_id"] == "tasks-ds-id"
    assert "failed" in result.output.lower()


def test_setup_notion_retries_on_unparseable_url(tmp_path):
    """If URL contains no 32-char hex ID, setup re-prompts without calling the API."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.configure._run_notion_discovery"), \
             patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input=(
                    "1\nmy-token\n\n"
                    "https://notion.so/workspace/no-id-here\n"
                    "https://notion.so/workspace/Tasks-abc123def456789012345678901234ab\n"
                    "https://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n"
                ),
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["tasks_ds_id"] == "tasks-ds-id"
    assert "failed" in result.output.lower()
