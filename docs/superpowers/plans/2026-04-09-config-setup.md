# Config Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a JSON-based, env-switched config system into the Wizard MCP server using `pydantic-settings`.

**Architecture:** `_config_path()` resolves the config file at instantiation time via `WIZARD_CONFIG_FILE` override (testing), `WIZARD_ENV=production` (`~/.wizard/config.json`), or dev default (`./config.json` at repo root). `Settings` reads that JSON file via `settings_customise_sources`. `server.py` instantiates `Settings` once at startup.

**Tech Stack:** Python 3.14, pydantic-settings v2, pytest, uv

---

### Task 1: Housekeeping — pyproject.toml, .gitignore, test layout

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add `pydantic-settings` and `pytest` to pyproject.toml**

Replace the contents of `pyproject.toml` with:

```toml
[project]
name = "wizard"
version = "1.2.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "fastmcp[tasks]>=3.2.0",
    "pydantic-settings>=2.0",
]

[dependency-groups]
dev = [
    "pytest>=9.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Add `config.json` to .gitignore**

Append to `.gitignore`:

```
# Wizard local config (contains secrets)
config.json
```

- [ ] **Step 3: Create the tests package**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 4: Sync dependencies**

```bash
uv sync
```

Expected: installs `pydantic-settings` and `pytest`, no errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore tests/__init__.py
git commit -m "chore: add pydantic-settings dep, pytest, gitignore config.json"
```

---

### Task 2: Write failing tests for config

**Files:**
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import json
import os
import pytest
from pathlib import Path


def test_config_path_returns_dev_path_by_default(monkeypatch):
    monkeypatch.delenv("WIZARD_ENV", raising=False)
    monkeypatch.delenv("WIZARD_CONFIG_FILE", raising=False)

    from src.config import _config_path

    result = _config_path()

    assert result == Path(__file__).parent.parent / "config.json"


def test_config_path_returns_prod_path(monkeypatch):
    monkeypatch.setenv("WIZARD_ENV", "production")
    monkeypatch.delenv("WIZARD_CONFIG_FILE", raising=False)

    from src.config import _config_path

    result = _config_path()

    assert result == Path.home() / ".wizard" / "config.json"


def test_config_path_override_takes_precedence(monkeypatch, tmp_path):
    override = str(tmp_path / "custom.json")
    monkeypatch.setenv("WIZARD_CONFIG_FILE", override)

    from src.config import _config_path

    result = _config_path()

    assert result == Path(override)


def test_settings_loads_values_from_json(monkeypatch, tmp_path):
    config = {"name": "My Server", "version": "2.0.0", "log_level": "DEBUG"}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    # Force reimport so settings_customise_sources picks up the new env var
    import importlib
    import src.config
    importlib.reload(src.config)
    from src.config import Settings

    settings = Settings()

    assert settings.name == "My Server"
    assert settings.version == "2.0.0"
    assert settings.log_level == "DEBUG"


def test_settings_uses_defaults_when_config_file_missing(monkeypatch, tmp_path):
    missing = tmp_path / "nonexistent.json"
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(missing))

    import importlib
    import src.config
    importlib.reload(src.config)
    from src.config import Settings

    settings = Settings()

    assert settings.name == "Wizard MCP Server"
    assert settings.version == "1.2.0"
    assert settings.log_level == "INFO"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ImportError` or `AttributeError` — `_config_path` does not exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_config.py
git commit -m "test: add failing tests for config path resolution and Settings loading"
```

---

### Task 3: Implement `src/config.py`

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Rewrite `src/config.py`**

```python
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, JsonConfigSettingsSource


def _config_path() -> Path:
    if override := os.getenv("WIZARD_CONFIG_FILE"):
        return Path(override)
    if os.getenv("WIZARD_ENV", "development") == "production":
        return Path.home() / ".wizard" / "config.json"
    return Path(__file__).parent.parent / "config.json"


class Settings(BaseSettings):
    name: str = Field(default="Wizard MCP Server")
    version: str = Field(default="1.2.0")
    log_level: str = Field(default="INFO")

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):
        return (JsonConfigSettingsSource(settings_cls, json_file=_config_path()),)
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat: implement config path resolution and Settings with JSON source"
```

---

### Task 4: Wire `server.py` to use `Settings`

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Update `server.py`**

```python
from fastmcp import FastMCP

from src.config import Settings

settings = Settings()

mcp = FastMCP(
    name=settings.name,
    instructions="Wizard is a set of tools used by Kiran Capoor to enhance his workflows and build contexts before doing any engineering workflows. This is significantly helpful for Kiran since he has ADHD.",
    version=settings.version,
)


@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}"


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 2: Verify the server starts**

```bash
uv run python server.py --help
```

Expected: FastMCP help output, no errors.

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: wire server.py to load name and version from Settings"
```

---

### Task 5: Add `config.example.json`

**Files:**
- Create: `config.example.json`

- [ ] **Step 1: Create the example config**

Create `config.example.json` at the repo root:

```json
{
  "name": "Wizard MCP Server",
  "version": "1.2.0",
  "log_level": "INFO"
}
```

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add config.example.json
git commit -m "chore: add config.example.json template"
```

---

## Dev Setup (for reference)

```bash
cp config.example.json config.json
# edit config.json with real values
uv run python server.py
```
