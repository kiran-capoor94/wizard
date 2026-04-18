import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.exceptions import Exit as ClickExit
from notion_client.errors import APIResponseError
from typer.testing import CliRunner

from wizard.cli.configure import run_notion_discovery
from wizard.cli.doctor import _check_jira_token, _check_notion_token
from wizard.cli.main import app


class TestCheckNotionToken:
    def test_empty_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings:
            MockSettings.return_value.notion.token.get_secret_value.return_value = ""
            passed, message = _check_notion_token()
            assert not passed
            assert "not set" in message

    def test_valid_token_passes(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.NotionSdkClient") as MockClient:
            MockSettings.return_value.notion.token.get_secret_value.return_value = "ntn_test"
            MockClient.return_value.users.me.return_value = {"id": "u1"}
            passed, message = _check_notion_token()
            assert passed
            assert "valid" in message

    def test_invalid_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.NotionSdkClient") as MockClient:
            MockSettings.return_value.notion.token.get_secret_value.return_value = "ntn_bad"
            MockClient.return_value.users.me.side_effect = APIResponseError(
                code="unauthorized",
                status=401,
                message="API token is invalid.",
                headers=MagicMock(),
                raw_body_text="",
            )
            passed, message = _check_notion_token()
            assert not passed
            assert "invalid" in message

    def test_network_error_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.NotionSdkClient") as MockClient:
            MockSettings.return_value.notion.token.get_secret_value.return_value = "ntn_test"
            MockClient.return_value.users.me.side_effect = httpx.ConnectError("timeout")
            passed, message = _check_notion_token()
            assert not passed
            assert "network" in message.lower() or "reach" in message.lower()


class TestCheckJiraToken:
    def test_empty_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = ""
            s.jira.base_url = ""
            s.jira.email = ""
            passed, message = _check_jira_token()
            assert not passed
            assert "not set" in message

    def test_valid_token_passes(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.httpx") as mock_httpx:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "jira_token"
            s.jira.base_url = "https://test.atlassian.net"
            s.jira.email = "user@example.com"
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status.return_value = None
            mock_httpx.get.return_value = mock_response
            passed, message = _check_jira_token()
            assert passed
            assert "valid" in message

    def test_invalid_token_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.httpx") as mock_httpx:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "bad_token"
            s.jira.base_url = "https://test.atlassian.net"
            s.jira.email = "user@example.com"
            response = MagicMock()
            response.status_code = 401
            mock_httpx.get.return_value = response
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=response,
            )
            passed, message = _check_jira_token()
            assert not passed
            assert "invalid" in message

    def test_network_error_fails(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings, \
             patch("wizard.cli.doctor.httpx") as mock_httpx:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "jira_token"
            s.jira.base_url = "https://test.atlassian.net"
            s.jira.email = "user@example.com"
            mock_httpx.get.side_effect = httpx.ConnectError("timeout")
            passed, message = _check_jira_token()
            assert not passed
            assert "network" in message.lower() or "reach" in message.lower()

    def test_missing_base_url_skips_api_call(self):
        with patch("wizard.cli.doctor.Settings") as MockSettings:
            s = MockSettings.return_value
            s.jira.token.get_secret_value.return_value = "jira_token"
            s.jira.base_url = ""
            s.jira.email = "user@example.com"
            passed, message = _check_jira_token()
            assert not passed
            assert "not set" in message or "not configured" in message


class TestConfigureNotion:
    def test_configure_notion_calls_full_flow(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"notion": {"token": ""}}))

        with patch("wizard.cli.main.WIZARD_HOME", tmp_path), \
             patch("wizard.cli.main.configure_notion") as mock_configure:
            runner = CliRunner()
            runner.invoke(app, ["configure", "--notion"])
            mock_configure.assert_called_once()


@pytest.mark.integration
class TestNotionDataSourceDiscovery:
    """Live integration test against the real Notion API.

    Uses the token from ~/.wizard/config.json. Validates the entire
    discovery pipeline against real data.

    Run explicitly: uv run pytest -m integration -v -s
    Skipped in normal test runs.
    """

    @pytest.fixture
    def notion_client(self):
        config_path = Path.home() / ".wizard" / "config.json"
        if not config_path.exists():
            pytest.skip("No ~/.wizard/config.json found")
        with open(config_path) as f:
            cfg = json.load(f)
        token = cfg.get("notion", {}).get("token", "")
        if not token:
            pytest.skip("No Notion token configured")
        from notion_client import Client as NotionSdkClient

        return NotionSdkClient(auth=token)

    def test_discover_returns_real_data_sources(self, notion_client):
        from wizard.cli.configure import discover_data_sources

        all_ds = discover_data_sources(notion_client)

        assert len(all_ds) > 0, (
            "No data sources found — is the integration connected to any databases?"
        )

        for ds_id, ds_name in all_ds:
            assert isinstance(ds_id, str) and len(ds_id) > 0
            assert isinstance(ds_name, str) and len(ds_name) > 0

        print(f"\n  Found {len(all_ds)} data sources:")
        for ds_id, ds_name in all_ds:
            print(f"    {ds_name} -- {ds_id}")

    def test_discovered_ds_ids_work_for_schema_retrieval(self, notion_client):
        from wizard.cli.configure import discover_data_sources

        all_ds = discover_data_sources(notion_client)
        assert len(all_ds) > 0, "No data sources to test"

        ds_id, ds_name = all_ds[0]
        schema = notion_client.data_sources.retrieve(data_source_id=ds_id)

        assert "properties" in schema, f"No properties for {ds_name}"
        props = schema["properties"]
        assert len(props) > 0, f"Empty properties for {ds_name}"

        print(f"\n  Schema for \"{ds_name}\" ({ds_id}):")
        for name, prop in props.items():
            print(f"    {name}: {prop['type']}")

    def test_filtering_finds_candidates(self, notion_client):
        from wizard.cli.configure import discover_data_sources

        all_ds = discover_data_sources(notion_client)
        assert len(all_ds) > 0

        for search_term in ("task", "meeting"):
            matches = [
                (ds_id, name) for ds_id, name in all_ds
                if search_term in name.lower()
            ]
            if matches:
                print(f"\n  '{search_term}' matched {len(matches)}:")
                for _, name in matches:
                    print(f"    {name}")
            else:
                print(f"\n  '{search_term}' matched 0 -- would show all {len(all_ds)}")


class TestNotionDiscoveryHardFail:
    def test_empty_properties_exits(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "notion": {"token": "ntn_test", "tasks_ds_id": "ds1", "meetings_ds_id": "ds2"},
        }))

        with patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure.notion_discovery") as mock_disc:
            mock_disc.fetch_db_properties.return_value = {}
            with pytest.raises(ClickExit):
                run_notion_discovery(config_path)

    def test_unmatched_required_field_exits(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "notion": {"token": "ntn_test", "tasks_ds_id": "ds1", "meetings_ds_id": "ds2"},
        }))

        available = {"Status": "status", "Priority": "select"}

        with patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure.notion_discovery") as mock_disc:
            mock_disc.fetch_db_properties.return_value = available
            mock_disc.match_properties.return_value = {
                "task_name": None,
                "task_status": "Status",
                "task_priority": "Priority",
                "task_due_date": None,
                "task_jira_key": None,
                "meeting_title": None,
                "meeting_category": None,
                "meeting_date": None,
                "meeting_url": None,
                "meeting_summary": None,
            }
            with pytest.raises(ClickExit):
                run_notion_discovery(config_path)

    def test_all_required_matched_saves_schema(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "notion": {"token": "ntn_test", "tasks_ds_id": "ds1", "meetings_ds_id": "ds2"},
        }))

        available = {"Task": "title", "Status": "status", "Meeting name": "title"}
        matches = {
            "task_name": "Task",
            "task_status": "Status",
            "task_priority": None,
            "task_due_date": None,
            "task_jira_key": None,
            "meeting_title": "Meeting name",
            "meeting_category": None,
            "meeting_date": None,
            "meeting_url": None,
            "meeting_summary": None,
        }

        with patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure.notion_discovery") as mock_disc:
            mock_disc.fetch_db_properties.return_value = available
            mock_disc.match_properties.return_value = matches
            run_notion_discovery(config_path)

        saved = json.loads(config_path.read_text())
        schema = saved["notion"]["notion_schema"]
        assert schema["task_name"] == "Task"
        assert schema["task_status"] == "Status"
        assert schema["meeting_title"] == "Meeting name"
        assert "task_priority" not in schema  # None values excluded
