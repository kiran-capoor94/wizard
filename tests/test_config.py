import json


def test_jira_settings_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    import sys
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    from src.config import settings

    assert settings.jira.base_url == ""
    assert settings.jira.token == ""
    assert settings.jira.project_key == ""


def test_scrubbing_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    import sys
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    from src.config import settings

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
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    from src.config import settings

    assert settings.jira.base_url == "https://jira.example.com"
    assert settings.jira.token == "tok"
    assert settings.scrubbing.allowlist == ["SISU", "AUTH-\\d+"]


def test_notion_has_db_ids(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "db": ":memory:",
        "notion": {
            "tasks_db_id": "abc-123",
            "meetings_db_id": "def-456",
            "token": "tok",
        }
    }))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))
    import sys
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    from src.config import settings
    assert settings.notion.tasks_db_id == "abc-123"
    assert settings.notion.meetings_db_id == "def-456"


def test_krisp_settings_removed(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))
    import sys
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    from src.config import settings
    assert not hasattr(settings, "krisp")
