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
    "model": "ollama/gemma4:latest-64k",
    "context_chars": 200000,
    "backends": [
      {
        "model": "ollama/gemma4:latest-64k",
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
  "sentry": {
    "dsn": "",
    "enabled": false,
    "traces_sample_rate": 0.1,
    "profiles_sample_rate": 0.1
  },
  "paths": {
    "installed_skills": "~/.wizard/skills",
    "package_skills": "<package>/wizard/skills",
    "sessions_dir": "~/.wizard/sessions"
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

**`scrubbing.allowlist`** — list of Python regex patterns. Matching text is
not scrubbed. Example: `["ENG-\\d+"]` preserves Jira keys.

**`synthesis.model`** — default `"ollama/gemma4:latest-64k"`. Must include a
provider prefix (`<provider>/<model>`).

**`synthesis.context_chars`** — maximum characters per synthesis chunk.
Default `200000`. Increase for larger local servers (e.g. Unsloth configured
for 262144 context).

**`synthesis.provider`** (deprecated) — kept for backwards compatibility.
The `migrate_provider` validator prepends it to `model` if `model` has no
`/` prefix. Use the `<provider>/<model>` form in `model` for new configs.

**`sentry`** — opt-in telemetry. Disabled by default. Set `dsn` to your
Sentry DSN and `enabled: true` to activate. `traces_sample_rate` and
`profiles_sample_rate` default to `0.1`.

**`paths`** — filesystem paths used by wizard at runtime:
- `installed_skills` — user-installed skills directory (default `~/.wizard/skills`)
- `package_skills` — skills bundled with the installed package
- `sessions_dir` — directory for session artefacts (default `~/.wizard/sessions`)
