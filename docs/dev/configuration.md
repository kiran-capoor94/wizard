# Configuration Schema — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Configuration Schema

Config file: `~/.wizard/config.json` (override: `WIZARD_CONFIG_FILE` env var)

```json
{
  "db": "~/.wizard/wizard.db",
  "knowledge_store": {
    "type": "",
    "notion": {
      "daily_parent_id": "",
      "tasks_db_id": "",
      "meetings_db_id": ""
    },
    "obsidian": {
      "vault_path": "",
      "daily_notes_folder": "Daily",
      "tasks_folder": "Tasks"
    }
  },
  "scrubbing": {
    "enabled": true,
    "allowlist": []
  },
  "synthesis": {
    "enabled": true,
    "backends": [
      {
        "model": "ollama/qwen3.5:4b",
        "base_url": "http://localhost:11434",
        "api_key": "",
        "description": "Local Ollama (primary)"
      },
      {
        "model": "gemini/gemini-2.5-flash-lite",
        "api_key": "",
        "description": "Cloud fallback"
      }
    ]
  },
  "modes": {
    "default": null,
    "allowed": ["architect", "ideation", "product-owner", "caveman"]
  }
}
```

`knowledge_store.type` is `"notion"`, `"obsidian"`, or `""` (disabled).
Configure interactively with `wizard configure knowledge-store`.
The knowledge store is optional — core Wizard works without it.
