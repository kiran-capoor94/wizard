import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.exceptions import Exit as ClickExit

from wizard.cli.configure import run_notion_discovery


def test_doctor_has_no_integration_checks():
    from wizard.cli.doctor import run_checks

    check_names = [c[0] for c in run_checks(stop_on_failure=False)]
    assert "Notion token" not in check_names
    assert "Jira token" not in check_names
    assert "Notion schema" not in check_names


def test_doctor_has_ks_check():
    from wizard.cli.doctor import run_checks

    check_names = [c[0] for c in run_checks(stop_on_failure=False)]
    assert "Knowledge store" in check_names


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
             patch("wizard.cli.configure.fetch_db_properties", return_value={}):
            with pytest.raises(ClickExit):
                run_notion_discovery(config_path)

    def test_unmatched_required_field_exits(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({
            "notion": {"token": "ntn_test", "tasks_ds_id": "ds1", "meetings_ds_id": "ds2"},
        }))

        available = {"Status": "status", "Priority": "select"}
        match_result = {
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

        with patch("wizard.cli.configure.NotionSdkClient"), \
             patch("wizard.cli.configure.fetch_db_properties", return_value=available), \
             patch("wizard.cli.configure.match_properties", return_value=match_result):
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
             patch("wizard.cli.configure.fetch_db_properties", return_value=available), \
             patch("wizard.cli.configure.match_properties", return_value=matches):
            run_notion_discovery(config_path)

        saved = json.loads(config_path.read_text())
        schema = saved["notion"]["notion_schema"]
        assert schema["task_name"] == "Task"
        assert schema["task_status"] == "Status"
        assert schema["meeting_title"] == "Meeting name"
        assert "task_priority" not in schema  # None values excluded
