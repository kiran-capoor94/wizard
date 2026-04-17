import json
from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def test_doctor_checks_wizard_home(tmp_path, monkeypatch):
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


def test_check_notion_schema_passes_when_live_db_matches(tmp_path, monkeypatch):
    """_check_notion_schema returns True when all expected properties exist with correct types."""
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
