# Config Setup Design

**Date:** 2026-04-09

## Context

`src/config.py` exists but is non-functional: `name` and `version` have no defaults, so `Settings()` raises immediately. `server.py` ignores config entirely and hardcodes all values. As integrations are added (Notion, Linear, etc.), the server will need API keys and tokens — these must not be committed to the repo.

The goal is a minimal, working config foundation: JSON-based, env-switched between dev (repo) and prod (`~/.wizard/`), with type-safe settings wired into the server.

## Approach

Pydantic Settings v2 with `json_file` support. A path resolver selects the config file based on `WIZARD_ENV`. No extra dependencies beyond `pydantic-settings` (already in use).

## Files

| File | Change |
|---|---|
| `src/config.py` | Rewrite: `SettingsConfigDict(json_file=...)`, path resolver, typed fields |
| `server.py` | Import `Settings`, use `settings.name` / `settings.version` |
| `config.example.json` | New: committed template with all keys |
| `.gitignore` | Add `config.json` |
| `pyproject.toml` | Add `pydantic-settings` as explicit dependency |

## Config Fields

```json
{
  "name": "Wizard MCP Server",
  "version": "1.2.0",
  "log_level": "INFO"
}
```

Future API keys are added as typed fields on `Settings` and placeholder keys in `config.example.json`.

## Path Resolution

```python
def _config_path() -> Path:
    if os.getenv("WIZARD_ENV", "development") == "production":
        return Path.home() / ".wizard" / "config.json"
    return Path(__file__).parent.parent / "config.json"
```

- `WIZARD_ENV=development` (default) → `./config.json` (repo root, gitignored)
- `WIZARD_ENV=production` → `~/.wizard/config.json`

## Dev Setup

```bash
cp config.example.json config.json
# edit config.json with real values
```

## Verification

1. `cp config.example.json config.json` and run `python server.py` — server starts without error
2. Remove `config.json` and run — should raise a clear Pydantic validation error
3. Set `WIZARD_ENV=production`, create `~/.wizard/config.json` — server reads from there
