# Setup & Uninstall Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shared MCP config helpers, wire MCP registration into `wizard setup`, and add a `wizard uninstall` command.

**Architecture:** A new `src/wizard/mcp_config.py` module owns all read/write logic for Claude config files. Both `setup` and `uninstall` in `cli/main.py` delegate to it. Tests use temp files — no real configs touched.

**Tech Stack:** Python 3, Typer, pathlib, json, shutil, pytest, typer.testing.CliRunner

---

## File Structure

| File | Role |
|------|------|
| `src/wizard/mcp_config.py` | **New** — MCP config read/write helpers |
| `src/wizard/cli/main.py` | **Modify** — add `uninstall` command, wire `register_wizard_mcp` into `setup` |
| `tests/test_mcp_config.py` | **New** — unit tests for mcp_config |
| `tests/test_cli.py` | **Modify** — integration tests for setup MCP registration and uninstall |

---

### Task 1: MCP Config Helper — Register

**Files:**
- Create: `src/wizard/mcp_config.py`
- Create: `tests/test_mcp_config.py`

- [ ] **Step 1: Write the failing test for `get_mcp_server_entry`**

```python
# tests/test_mcp_config.py
from wizard.mcp_config import get_mcp_server_entry


def test_get_mcp_server_entry_returns_uv_command():
    entry = get_mcp_server_entry()
    assert entry["command"] == "uv"
    assert "--directory" in entry["args"]
    assert "server.py" in entry["args"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp_config.py::test_get_mcp_server_entry_returns_uv_command -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wizard.mcp_config'`

- [ ] **Step 3: Write minimal `get_mcp_server_entry`**

```python
# src/wizard/mcp_config.py
from pathlib import Path

# Walk from src/wizard/mcp_config.py → project root
_PROJECT_DIR = Path(__file__).resolve().parents[2]

CLAUDE_CODE_CONFIG = Path.home() / ".claude.json"
CLAUDE_DESKTOP_CONFIG = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_mcp_server_entry() -> dict:
    """Return the wizard MCP server definition for Claude config files."""
    return {
        "command": "uv",
        "args": ["--directory", str(_PROJECT_DIR), "run", "server.py"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mcp_config.py::test_get_mcp_server_entry_returns_uv_command -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for `register_wizard_mcp`**

```python
# tests/test_mcp_config.py (append)
import json
from unittest.mock import patch
from wizard.mcp_config import register_wizard_mcp, CLAUDE_CODE_CONFIG, CLAUDE_DESKTOP_CONFIG


def _patch_config_paths(tmp_path):
    """Return a context-manager that redirects both config constants to temp files."""
    code_cfg = tmp_path / "claude.json"
    desktop_cfg = tmp_path / "claude_desktop_config.json"
    return (
        code_cfg,
        desktop_cfg,
        patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
        patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", desktop_cfg),
    )


def test_register_into_existing_config(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"someKey": True}))
    desktop_cfg.write_text(json.dumps({"preferences": {}}))

    with p1, p2:
        results = register_wizard_mcp()

    code_data = json.loads(code_cfg.read_text())
    assert "wizard" in code_data["mcpServers"]
    assert code_data["someKey"] is True  # existing keys preserved

    desktop_data = json.loads(desktop_cfg.read_text())
    assert "wizard" in desktop_data["mcpServers"]
    assert desktop_data["preferences"] == {}  # existing keys preserved

    assert len(results) == 2


def test_register_is_idempotent(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({}))
    desktop_cfg.write_text(json.dumps({}))

    with p1, p2:
        register_wizard_mcp()
        first = json.loads(code_cfg.read_text())
        register_wizard_mcp()
        second = json.loads(code_cfg.read_text())

    assert first == second


def test_register_skips_missing_file(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    # Neither file exists

    with p1, p2:
        results = register_wizard_mcp()

    assert len(results) == 0


def test_register_skips_invalid_json(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text("not json{{{")

    with p1, p2:
        results = register_wizard_mcp()

    assert len(results) == 0
    # File must not be corrupted
    assert code_cfg.read_text() == "not json{{{"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_config.py -v -k "register"`
Expected: FAIL — `ImportError: cannot import name 'register_wizard_mcp'`

- [ ] **Step 7: Implement `register_wizard_mcp`**

```python
# src/wizard/mcp_config.py (append)
import json
import logging
import sys

logger = logging.getLogger(__name__)

_CONFIG_TARGETS = {
    "Claude Code": CLAUDE_CODE_CONFIG,
    "Claude Desktop": CLAUDE_DESKTOP_CONFIG,
}


def register_wizard_mcp() -> list[str]:
    """Register the wizard MCP server in all existing Claude config files.

    Returns the list of target names where registration succeeded.
    """
    registered: list[str] = []
    entry = get_mcp_server_entry()

    for name, path in _CONFIG_TARGETS.items():
        if not path.exists():
            continue

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            print(f"  Warning: {path} is not valid JSON — skipping", file=sys.stderr)
            continue

        data.setdefault("mcpServers", {})
        data["mcpServers"]["wizard"] = entry
        path.write_text(json.dumps(data, indent=2) + "\n")
        registered.append(name)

    return registered
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_config.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/wizard/mcp_config.py tests/test_mcp_config.py
git commit -m "feat: add mcp_config module with get_mcp_server_entry and register_wizard_mcp"
```

---

### Task 2: MCP Config Helper — Deregister

**Files:**
- Modify: `src/wizard/mcp_config.py`
- Modify: `tests/test_mcp_config.py`

- [ ] **Step 1: Write failing tests for `deregister_wizard_mcp`**

```python
# tests/test_mcp_config.py (append)
from wizard.mcp_config import deregister_wizard_mcp


def test_deregister_removes_wizard_entry(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}, "other": {}}}))
    desktop_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))

    with p1, p2:
        results = deregister_wizard_mcp()

    code_data = json.loads(code_cfg.read_text())
    assert "wizard" not in code_data["mcpServers"]
    assert "other" in code_data["mcpServers"]

    desktop_data = json.loads(desktop_cfg.read_text())
    assert "mcpServers" not in desktop_data  # empty mcpServers removed

    assert len(results) == 2


def test_deregister_noop_when_no_wizard_entry(tmp_path):
    code_cfg, desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text(json.dumps({"mcpServers": {"other": {}}}))

    with p1, p2:
        results = deregister_wizard_mcp()

    assert len(results) == 0
    # File unchanged
    assert json.loads(code_cfg.read_text()) == {"mcpServers": {"other": {}}}


def test_deregister_skips_missing_file(tmp_path):
    _code_cfg, _desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)

    with p1, p2:
        results = deregister_wizard_mcp()

    assert len(results) == 0


def test_deregister_skips_invalid_json(tmp_path):
    code_cfg, _desktop_cfg, p1, p2 = _patch_config_paths(tmp_path)
    code_cfg.write_text("broken}")

    with p1, p2:
        results = deregister_wizard_mcp()

    assert len(results) == 0
    assert code_cfg.read_text() == "broken}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_config.py -v -k "deregister"`
Expected: FAIL — `ImportError: cannot import name 'deregister_wizard_mcp'`

- [ ] **Step 3: Implement `find_wizard_mcp_targets` and `deregister_wizard_mcp`**

```python
# src/wizard/mcp_config.py (append)

def find_wizard_mcp_targets() -> list[str]:
    """Return config target names that currently have a wizard MCP entry."""
    found: list[str] = []
    for name, path in _CONFIG_TARGETS.items():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            if "wizard" in data.get("mcpServers", {}):
                found.append(name)
        except (json.JSONDecodeError, ValueError):
            continue
    return found


def deregister_wizard_mcp() -> list[str]:
    """Remove the wizard MCP server from all Claude config files.

    Returns the list of target names where deregistration succeeded.
    """
    deregistered: list[str] = []

    for name, path in _CONFIG_TARGETS.items():
        if not path.exists():
            continue

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            print(f"  Warning: {path} is not valid JSON — skipping", file=sys.stderr)
            continue

        mcp_servers = data.get("mcpServers", {})
        if "wizard" not in mcp_servers:
            continue

        del mcp_servers["wizard"]
        if not mcp_servers:
            del data["mcpServers"]
        path.write_text(json.dumps(data, indent=2) + "\n")
        deregistered.append(name)

    return deregistered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/mcp_config.py tests/test_mcp_config.py
git commit -m "feat: add deregister_wizard_mcp to mcp_config module"
```

---

### Task 3: Wire MCP Registration Into `wizard setup`

**Files:**
- Modify: `src/wizard/cli/main.py:32-55`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for setup MCP registration**

```python
# tests/test_cli.py (append after existing setup tests)

def test_setup_registers_mcp_in_claude_configs(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    code_cfg = tmp_path / "claude.json"
    desktop_cfg = tmp_path / "desktop_config.json"
    code_cfg.write_text(json.dumps({}))
    desktop_cfg.write_text(json.dumps({}))

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", desktop_cfg),
        ):
            result = runner.invoke(ctx.app, ["setup"])

    assert result.exit_code == 0
    code_data = json.loads(code_cfg.read_text())
    assert "wizard" in code_data.get("mcpServers", {})
    assert "Claude Code" in result.output


def test_setup_skips_mcp_when_config_missing(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    code_cfg = tmp_path / "claude.json"  # does not exist
    desktop_cfg = tmp_path / "desktop_config.json"  # does not exist

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", desktop_cfg),
        ):
            result = runner.invoke(ctx.app, ["setup"])

    assert result.exit_code == 0
    assert not code_cfg.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py::test_setup_registers_mcp_in_claude_configs -v`
Expected: FAIL — no MCP registration in setup output

- [ ] **Step 3: Add `register_wizard_mcp` call to `setup` command**

In `src/wizard/cli/main.py`, add at the end of the `setup()` function, before the final "Setup complete." echo:

```python
    # Register MCP server in Claude config files
    from wizard.mcp_config import register_wizard_mcp

    registered = register_wizard_mcp()
    for name in registered:
        typer.echo(f"  Registered wizard MCP in {name}")
    if not registered:
        typer.echo("  No Claude config files found — MCP not registered. Run setup again after installing Claude.")
```

The full `setup()` function becomes:

```python
@app.command()
def setup() -> None:
    """Create ~/.wizard, default config, install skills, and register MCP."""
    WIZARD_HOME.mkdir(parents=True, exist_ok=True)

    config_path = WIZARD_HOME / "config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(_DEFAULT_CONFIG, indent=2))
        typer.echo(f"Created default config at {config_path}")
    else:
        typer.echo(f"Config already exists at {config_path}")

    # Copy skills from package to ~/.wizard/skills/
    source = _package_skills_dir()
    dest = WIZARD_HOME / "skills"
    if source.exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        typer.echo(f"Installed skills to {dest}")
    else:
        typer.echo("No skills found in package — skipping skill install")

    # Register MCP server in Claude config files
    from wizard.mcp_config import register_wizard_mcp

    registered = register_wizard_mcp()
    for name in registered:
        typer.echo(f"  Registered wizard MCP in {name}")
    if not registered:
        typer.echo("  No Claude config files found — MCP not registered. Run setup again after installing Claude.")

    typer.echo("Setup complete.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v -k "setup"`
Expected: All PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: wire MCP registration into wizard setup"
```

---

### Task 4: `wizard uninstall` Command

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for full uninstall with `--yes`**

```python
# tests/test_cli.py (append)

def test_uninstall_removes_wizard_dir_and_mcp(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")
    (wizard_dir / "wizard.db").write_text("")
    skills = wizard_dir / "skills" / "test-skill"
    skills.mkdir(parents=True)

    code_cfg = tmp_path / "claude.json"
    desktop_cfg = tmp_path / "desktop_config.json"
    code_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))
    desktop_cfg.write_text(json.dumps({"mcpServers": {"wizard": {"command": "uv"}}}))

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", desktop_cfg),
        ):
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert not wizard_dir.exists()
    assert "wizard" not in json.loads(code_cfg.read_text()).get("mcpServers", {})
    assert "wizard" not in json.loads(desktop_cfg.read_text()).get("mcpServers", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_uninstall_removes_wizard_dir_and_mcp -v`
Expected: FAIL — `No such command 'uninstall'`

- [ ] **Step 3: Write failing test for nothing-to-uninstall case**

```python
# tests/test_cli.py (append)

def test_uninstall_nothing_to_do(tmp_path):
    wizard_dir = tmp_path / ".wizard"  # does not exist
    code_cfg = tmp_path / "claude.json"  # does not exist
    desktop_cfg = tmp_path / "desktop_config.json"  # does not exist

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", desktop_cfg),
        ):
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert "nothing to uninstall" in result.output.lower()
```

- [ ] **Step 4: Write failing test for confirmation prompt (user says no)**

```python
# tests/test_cli.py (append)

def test_uninstall_aborts_without_confirmation(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", tmp_path / "nope.json"),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope2.json"),
        ):
            result = runner.invoke(ctx.app, ["uninstall"], input="n\n")

    assert result.exit_code == 0
    assert wizard_dir.exists()  # nothing deleted
```

- [ ] **Step 5: Write failing test for confirmation prompt (user says yes)**

```python
# tests/test_cli.py (append)

def test_uninstall_proceeds_with_confirmation(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", tmp_path / "nope.json"),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope2.json"),
        ):
            result = runner.invoke(ctx.app, ["uninstall"], input="y\n")

    assert result.exit_code == 0
    assert not wizard_dir.exists()
```

- [ ] **Step 6: Write failing test for partial state**

```python
# tests/test_cli.py (append)

def test_uninstall_partial_state(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")
    # No wizard.db, no skills, no MCP registrations

    code_cfg = tmp_path / "claude.json"
    code_cfg.write_text(json.dumps({"mcpServers": {"other": {}}}))  # no wizard entry

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", code_cfg),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope.json"),
        ):
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert not wizard_dir.exists()
    # Other MCP entries preserved
    assert json.loads(code_cfg.read_text()) == {"mcpServers": {"other": {}}}
```

- [ ] **Step 7: Write failing test for idempotency (uninstall after uninstall)**

```python
# tests/test_cli.py (append)

def test_uninstall_is_idempotent(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text("{}")

    with _fresh_app(wizard_dir) as ctx:
        with (
            patch("wizard.mcp_config.CLAUDE_CODE_CONFIG", tmp_path / "nope.json"),
            patch("wizard.mcp_config.CLAUDE_DESKTOP_CONFIG", tmp_path / "nope2.json"),
        ):
            runner.invoke(ctx.app, ["uninstall", "--yes"])
            result = runner.invoke(ctx.app, ["uninstall", "--yes"])

    assert result.exit_code == 0
    assert "nothing to uninstall" in result.output.lower()
```

- [ ] **Step 8: Run all uninstall tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v -k "uninstall"`
Expected: FAIL — `No such command 'uninstall'`

- [ ] **Step 9: Implement `uninstall` command**

In `src/wizard/cli/main.py`, add after the `doctor` command:

```python
@app.command()
def uninstall(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
) -> None:
    """Remove all Wizard runtime state and MCP registration."""
    from wizard.mcp_config import deregister_wizard_mcp, find_wizard_mcp_targets

    # Step 1: Gather what exists
    wizard_files = {
        "wizard.db": "all notes, sessions, meetings",
        "config.json": None,
        "skills/": None,
    }
    existing_files: list[tuple[str, str | None]] = []
    for name, desc in wizard_files.items():
        path = WIZARD_HOME / name.rstrip("/")
        if path.exists():
            existing_files.append((name, desc))

    mcp_targets = find_wizard_mcp_targets()

    has_wizard_dir = WIZARD_HOME.exists()
    has_anything = has_wizard_dir or bool(mcp_targets)

    if not has_anything:
        typer.echo("Nothing to uninstall.")
        return

    # Step 2: Confirmation prompt
    if not yes:
        typer.echo("This will permanently delete:")
        for name, desc in existing_files:
            suffix = f"  ({desc})" if desc else ""
            typer.echo(f"  ~/.wizard/{name}{suffix}")
        if has_wizard_dir and not existing_files:
            typer.echo("  ~/.wizard/")
        for name in mcp_targets:
            typer.echo(f"  wizard MCP entry from {name} config")
        typer.echo("")
        confirm = typer.prompt("Are you sure? [y/N]", default="N", show_default=False)
        if confirm.lower() != "y":
            typer.echo("Aborted.")
            return

    # Step 3: Execute
    deregistered = deregister_wizard_mcp()
    for name in deregistered:
        typer.echo(f"  Removed wizard MCP from {name}")

    if has_wizard_dir:
        shutil.rmtree(WIZARD_HOME)
        typer.echo(f"  Removed {WIZARD_HOME}")

    # Step 4: Summary
    typer.echo("Wizard uninstalled. Run `pip uninstall wizard` to remove the package.")
```

- [ ] **Step 10: Run all uninstall tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v -k "uninstall"`
Expected: All PASS

- [ ] **Step 11: Run full test suite**

Run: `uv run pytest -v`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: add wizard uninstall command"
```
