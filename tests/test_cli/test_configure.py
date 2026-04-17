import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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


# --- sync command tests ---


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
    from tests.helpers import mock_session
    from wizard.schemas import SourceSyncStatus

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


# --- configure --notion tests ---


def test_configure_notion_runs_discovery(tmp_path):
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
        with patch("wizard.cli.configure.notion_discovery") as mock_nd, \
             patch("wizard.cli.configure.NotionSdkClient"):
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


def test_configure_notion_prints_arrow_format(tmp_path):
    """_run_notion_discovery prints matched fields as 'field → Property'."""
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
        with patch("wizard.cli.configure.notion_discovery") as mock_nd, \
             patch("wizard.cli.configure.NotionSdkClient"):
            mock_nd.fetch_db_properties.return_value = {"Task": "title", "Status": "status"}
            mock_nd.match_properties.return_value = {
                "task_name": "Task", "task_status": "Status",
                "task_priority": None, "task_due_date": None,
                "task_jira_key": None, "meeting_title": "Meeting name",
                "meeting_category": None, "meeting_date": None,
                "meeting_url": None, "meeting_summary": None,
            }
            result = runner.invoke(ctx.app, ["configure", "--notion"])

    assert "→" in result.output
    assert "task_name" in result.output
    assert "Schema saved" in result.output


def test_configure_jira_prompts_and_saves_fields(tmp_path):
    """configure --jira re-prompts all Jira fields and saves them."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text(json.dumps({"jira": {}, "notion": {}, "scrubbing": {}}))

    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(
            ctx.app, ["configure", "--jira"],
            input="https://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
        )

    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["jira"]["base_url"] == "https://acme.atlassian.net"
    assert cfg["jira"]["project_key"] == "ENG"
    assert cfg["jira"]["email"] == "dev@acme.com"
    assert cfg["jira"]["token"] == "jira-token"


def test_configure_no_flags_shows_available_options(tmp_path):
    """configure with no flags prints both --notion and --jira as available."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(ctx.app, ["configure"])
    assert "--notion" in result.output
    assert "--jira" in result.output


# --- _resolve_notion_page_id tests ---


def test_resolve_notion_page_id_extracts_from_workspace_url():
    from wizard.cli.configure import resolve_notion_page_id
    url = "https://www.notion.so/workspace/My-Tasks-abc123def456789012345678901234ab"
    assert resolve_notion_page_id(url) == "abc123de-f456-7890-1234-5678901234ab"


def test_resolve_notion_page_id_extracts_from_short_url():
    from wizard.cli.configure import resolve_notion_page_id
    url = "https://www.notion.so/abc123def456789012345678901234ab"
    assert resolve_notion_page_id(url) == "abc123de-f456-7890-1234-5678901234ab"


def test_resolve_notion_page_id_strips_query_params():
    from wizard.cli.configure import resolve_notion_page_id
    url = "https://www.notion.so/My-Tasks-abc123def456789012345678901234ab?v=xyz&p=foo"
    assert resolve_notion_page_id(url) == "abc123de-f456-7890-1234-5678901234ab"


def test_resolve_notion_page_id_raises_on_invalid_url():
    from wizard.cli.configure import resolve_notion_page_id
    with pytest.raises(ValueError, match="Could not extract"):
        resolve_notion_page_id("https://notion.so/workspace/no-id-here")


# --- _resolve_ds_id tests ---


def test_resolve_ds_id_returns_page_id_on_success():
    from wizard.cli.configure import resolve_ds_id
    client = MagicMock()
    page_id = "abc123de-f456-7890-1234-5678901234ab"
    result = resolve_ds_id(client, page_id)
    assert result == page_id
    client.data_sources.retrieve.assert_called_once_with(data_source_id=page_id)


def test_resolve_ds_id_raises_on_api_error():
    from wizard.cli.configure import resolve_ds_id
    client = MagicMock()
    client.data_sources.retrieve.side_effect = Exception("API error: 404 not found")
    with pytest.raises(Exception, match="404"):
        resolve_ds_id(client, "abc123de-f456-7890-1234-5678901234ab")
