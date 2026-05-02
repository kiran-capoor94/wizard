# Config — AI Fact Sheet

## Config File Location

- Default: `~/.wizard/config.json`
- Override: `WIZARD_CONFIG_FILE` env var
- Missing file → all defaults applied; no error raised

## Loading Mechanism

- `JsonConfigSettingsSource` (custom `PydanticBaseSettingsSource`) reads the JSON file and returns it as a dict merged into pydantic-settings.
- `env_settings`, `dotenv_settings`, and `file_secret_settings` sources are **disabled** — `settings_customise_sources` returns only `(JsonConfigSettingsSource(settings_cls),)`.
- `Settings.model_config = {"extra": "ignore"}` — unknown keys in config.json are silently dropped.

## `Settings` (top-level)

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | `"wizard"` | Server name |
| `version` | `str` | `"2.2.3"` | Server version |
| `db` | `str` | `~/.wizard/wizard.db` | SQLite database path |
| `scrubbing` | `ScrubbingSettings` | see below | PII scrubbing config |
| `knowledge_store` | `KnowledgeStoreSettings` | see below | External KS config |
| `synthesis` | `SynthesisSettings` | see below | LLM synthesis config |
| `sentry` | `SentrySettings` | see below | Error tracking config |
| `modes` | `ModesSettings` | see below | Session mode config |
| `paths` | `WizardPaths` | see below | Filesystem paths |

## `ScrubbingSettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | `bool` | `True` | Whether PII scrubbing is active |
| `allowlist` | `list[str]` | `[]` | Terms exempt from scrubbing |

## `SynthesisSettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | `str` | `""` | **Deprecated** — kept so old configs don't error on load |
| `model` | `str` | `"ollama/gemma4:latest-64k"` | LiteLLM model string (must include `provider/` prefix) |
| `base_url` | `str` | `"http://localhost:11434"` | Inference server base URL |
| `api_key` | `str` | `""` | API key (empty = no auth) |
| `enabled` | `bool` | `True` | Whether synthesis runs at session end |
| `context_chars` | `int` | `200000` | Max characters per chunk sent to model |
| `backends` | `list[BackendConfig]` | `[]` | Ordered fallback backends; first healthy wins |

**`provider` deprecation / `migrate_provider` validator:**
- `@model_validator(mode="before")` runs before field assignment.
- If `provider` is set **and** `model` has no `/` in it → prepends `provider/` to `model`.
- If `provider` is not set but `model` has no `/` → logs a warning about incorrect LiteLLM routing; does **not** raise.
- If `model` already contains `/` → no mutation regardless of `provider`.

## `BackendConfig`

| Field | Type | Default | Description |
|---|---|---|---|
| `model` | `str` | `""` | LiteLLM model string |
| `base_url` | `str` | `""` | Base URL for this backend |
| `api_key` | `str` | `""` | API key |
| `provider` | `str` | `""` | Informational only — routing is via `model` prefix |
| `description` | `str` | `""` | Human-readable label shown in logs |

## `KnowledgeStoreSettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | `str` | `""` | Active backend: `"notion"`, `"obsidian"`, or `""` (disabled) |
| `notion` | `NotionKSSettings` | see below | Notion-specific settings |
| `obsidian` | `ObsidianKSSettings` | see below | Obsidian-specific settings |

## `NotionKSSettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `daily_parent_id` | `str` | `""` | Notion page ID for daily note parent |
| `tasks_db_id` | `str` | `""` | Notion database ID for tasks |
| `meetings_db_id` | `str` | `""` | Notion database ID for meetings |

## `ObsidianKSSettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `vault_path` | `str` | `""` | Absolute path to Obsidian vault root |
| `daily_notes_folder` | `str` | `"Daily"` | Subfolder for daily notes |
| `tasks_folder` | `str` | `"Tasks"` | Subfolder for task notes |

## `SentrySettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `dsn` | `str` | `""` | Sentry DSN |
| `enabled` | `bool` | `False` | Whether Sentry is active |
| `traces_sample_rate` | `float` | `0.1` | Trace sample rate (0–1) |
| `profiles_sample_rate` | `float` | `0.1` | Profile sample rate (0–1) |

## `ModesSettings`

| Field | Type | Default | Description |
|---|---|---|---|
| `default` | `str \| None` | `None` | Mode applied automatically at session start |
| `allowed` | `list[str]` | `["architect", "ideation", "product-owner", "caveman"]` | Modes available in this install |

## `WizardPaths`

**Frozen** (`model_config = {"frozen": True}`) — immutable after construction.

| Field | Type | Default | Description |
|---|---|---|---|
| `installed_skills` | `Path` | `~/.wizard/skills` | User-installed skill files |
| `package_skills` | `Path` | `<package_dir>/skills` | Built-in skills shipped with wizard |
| `sessions_dir` | `Path` | `~/.wizard/sessions` | Per-session artefact storage (transcripts, etc.) |

## `WIZARD_MODES` Constant

```python
WIZARD_MODES: list[str] = ["architect", "ideation", "product-owner", "caveman"]
```

Four values — mirrors `ModesSettings.allowed` default.
