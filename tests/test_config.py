import json
import os

from wizard.config import Settings


def test_settings_has_no_jira_or_notion(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({}))
    os.environ["WIZARD_CONFIG_FILE"] = str(cfg)
    s = Settings()
    assert not hasattr(s, "jira")
    assert not hasattr(s, "notion")


def test_settings_knowledge_store_defaults():
    s = Settings()
    assert s.knowledge_store.type == ""
    assert s.knowledge_store.notion.daily_parent_id == ""
    assert s.knowledge_store.obsidian.vault_path == ""


def test_settings_knowledge_store_from_config(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "knowledge_store": {
            "type": "notion",
            "notion": {"daily_parent_id": "abc", "tasks_db_id": "def"}
        }
    }))
    os.environ["WIZARD_CONFIG_FILE"] = str(cfg)
    s = Settings()
    assert s.knowledge_store.type == "notion"
    assert s.knowledge_store.notion.daily_parent_id == "abc"
    assert s.knowledge_store.notion.tasks_db_id == "def"
