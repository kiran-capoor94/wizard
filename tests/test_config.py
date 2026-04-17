import json


def test_jira_settings_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    import sys
    monkeypatch.delitem(sys.modules, "wizard.config", raising=False)
    from wizard.config import settings

    assert settings.jira.base_url == ""
    assert settings.jira.token.get_secret_value() == ""
    assert settings.jira.project_key == ""


def test_scrubbing_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    import sys
    monkeypatch.delitem(sys.modules, "wizard.config", raising=False)
    from wizard.config import settings

    assert settings.scrubbing.enabled is True
    assert settings.scrubbing.allowlist == []


def test_nested_config_from_json(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "db": ":memory:",
        "jira": {"base_url": "https://jira.example.com", "token": "tok", "project_key": "ENG"},
        "scrubbing": {"enabled": True, "allowlist": ["SISU", "AUTH-\\d+"]}
    }))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    import sys
    monkeypatch.delitem(sys.modules, "wizard.config", raising=False)
    from wizard.config import settings

    assert settings.jira.base_url == "https://jira.example.com"
    assert settings.jira.token.get_secret_value() == "tok"
    assert settings.scrubbing.allowlist == ["SISU", "AUTH-\\d+"]


def test_notion_has_db_ids(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "db": ":memory:",
        "notion": {
            "tasks_ds_id": "abc-123",
            "meetings_ds_id": "def-456",
            "token": "tok",
        }
    }))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))
    import sys
    monkeypatch.delitem(sys.modules, "wizard.config", raising=False)
    from wizard.config import settings
    assert settings.notion.tasks_ds_id == "abc-123"
    assert settings.notion.meetings_ds_id == "def-456"


def test_notion_has_daily_page_parent_id():
    from wizard.config import NotionSettings
    s = NotionSettings()
    assert hasattr(s, "daily_page_parent_id")
    assert s.daily_page_parent_id == ""


def test_krisp_settings_removed(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))
    import sys
    monkeypatch.delitem(sys.modules, "wizard.config", raising=False)
    from wizard.config import settings
    assert not hasattr(settings, "krisp")


def test_notion_schema_defaults():
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings()
    assert schema.task_name == "Task"
    assert schema.task_status == "Status"
    assert schema.task_priority == "Priority"
    assert schema.task_due_date == "Due date"
    assert schema.task_jira_key == "Jira"
    assert schema.meeting_title == "Meeting name"
    assert schema.meeting_date == "Date"
    assert schema.meeting_url == "Krisp URL"
    assert schema.meeting_summary == "Summary"


def test_notion_settings_has_schema():
    from wizard.config import NotionSettings, NotionSchemaSettings
    notion = NotionSettings()
    assert hasattr(notion, "notion_schema")
    assert isinstance(notion.notion_schema, NotionSchemaSettings)


def test_notion_schema_has_meeting_category_field():
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings()
    assert hasattr(schema, "meeting_category")
    assert schema.meeting_category == "Category"


def test_token_is_secret_str():
    from pydantic import SecretStr
    from wizard.config import JiraSettings, NotionSettings

    j = JiraSettings()
    n = NotionSettings()
    assert isinstance(j.token, SecretStr)
    assert isinstance(n.token, SecretStr)
    assert j.token.get_secret_value() == ""
    assert n.token.get_secret_value() == ""
