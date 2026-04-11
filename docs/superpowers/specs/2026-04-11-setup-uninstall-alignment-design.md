# Setup & Uninstall Alignment — Design Spec

**Status:** Design  
**Scope:** Align `wizard setup` to register MCP across both Claude configs; add `wizard uninstall` as the inverse operation.

---

## 1. Problem

`wizard setup` creates `~/.wizard/` and its contents but does not register the MCP server in either Claude config file. Registration is currently manual. There is no `wizard uninstall` command at all.

This spec adds:
1. A shared MCP config helper module
2. MCP registration to `wizard setup`
3. A new `wizard uninstall` command

---

## 2. MCP Config Helper — `src/wizard/mcp_config.py`

### 2.1 Config Targets

| Constant | Path | Client |
|----------|------|--------|
| `CLAUDE_CODE_CONFIG` | `~/.claude.json` | Claude Code CLI |
| `CLAUDE_DESKTOP_CONFIG` | `~/.config/Claude/claude_desktop_config.json` | Claude Desktop |

### 2.2 Functions

**`get_mcp_server_entry() -> dict`**

Returns the wizard MCP server definition:
```python
{
    "command": "uv",
    "args": ["--directory", str(project_dir), "run", "server.py"]
}
```

Where `project_dir` is determined by `Path(__file__).resolve().parents[2]` — walking up from `src/wizard/mcp_config.py` to the project root. This matches how `server.py` is located relative to the package.

**`register_wizard_mcp() -> list[str]`**

For each config target:
1. If file doesn't exist → skip, return a skip message for that target
2. Read file, parse JSON
3. If JSON is invalid → warn, skip that file
4. Set `mcpServers.wizard` to the entry from `get_mcp_server_entry()` (overwrites if present — idempotent)
5. Write back
6. Return list of registered target names

**`deregister_wizard_mcp() -> list[str]`**

For each config target:
1. If file doesn't exist → skip
2. Read file, parse JSON
3. If JSON is invalid → warn, skip
4. If `mcpServers.wizard` exists → remove it
5. If `mcpServers` is now empty → remove the `mcpServers` key
6. Write back
7. Return list of deregistered target names

### 2.3 Edge Cases

- File doesn't exist → skip, no error
- File exists but isn't valid JSON → warn to stderr, skip that file, don't corrupt it
- File is read-only → let the OS error propagate to the caller
- Re-running register/deregister → idempotent, same result

---

## 3. `wizard setup` Changes

Existing behavior is unchanged:
- Creates `~/.wizard/`
- Writes default `config.json` if missing
- Copies skills to `~/.wizard/skills/`
- DB auto-creates on first connection

**New step added after existing setup**:
- Call `register_wizard_mcp()`
- Print which targets were registered: `"Registered wizard MCP in Claude Code"`
- For skipped targets, print guidance: `"Claude Desktop config not found — run setup again after installing Claude Desktop."`

Setup remains idempotent. Re-running updates the MCP entry path if the project directory has moved.

---

## 4. `wizard uninstall` Command

### 4.1 Signature

```python
@app.command()
def uninstall(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
) -> None:
```

### 4.2 Flow

**Step 1 — Gather existing state**

Check each target:
- `~/.wizard/` and its contents (wizard.db, config.json, skills/)
- wizard entry in each MCP config file

Build a list of what will be deleted. If nothing exists, print `"Nothing to uninstall."` and exit cleanly (code 0).

**Step 2 — Confirmation prompt** (unless `--yes`)

```
This will permanently delete:
  ~/.wizard/wizard.db  (all notes, sessions, meetings)
  ~/.wizard/config.json
  ~/.wizard/skills/
  wizard MCP entry from Claude Code config
  wizard MCP entry from Claude Desktop config

Are you sure? [y/N]:
```

Only lists items that actually exist. User must type `y` or `Y` to proceed. Anything else aborts.

**Step 3 — Execute**

1. Call `deregister_wizard_mcp()` — print each deregistered target
2. Delete `~/.wizard/` recursively via `shutil.rmtree`
3. Print each completed step

**Step 4 — Summary**

```
Wizard uninstalled. Run `pip uninstall wizard` to remove the package.
```

### 4.3 What It Does NOT Do

- Does not run `pip uninstall wizard`
- Does not touch any other keys in the config files
- Does not delete anything outside `~/.wizard/` and the two MCP config entries

### 4.4 Idempotency

Running uninstall twice: the second run finds nothing and prints `"Nothing to uninstall."` with exit code 0.

---

## 5. Testing Strategy

### 5.1 `mcp_config.py` Unit Tests

All tests use temp files — no real config files touched.

| Test | Assertion |
|------|-----------|
| Register into existing config | `mcpServers.wizard` key present with correct entry |
| Register twice | Idempotent — same JSON output |
| Register when file missing | Skipped, no error, returned in skip list |
| Register when file has invalid JSON | Warned, skipped, file untouched |
| Deregister existing entry | `mcpServers.wizard` removed |
| Deregister when no wizard entry | No-op, no error |
| Deregister leaves empty mcpServers | `mcpServers` key removed entirely |
| Deregister when file missing | Skipped, no error |

### 5.2 `wizard setup` Integration Tests

| Test | Assertion |
|------|-----------|
| Setup creates ~/.wizard/ and registers MCP | Directory exists, MCP entries present in temp config files |
| Re-running setup is idempotent | Same result, no errors |

### 5.3 `wizard uninstall` Integration Tests

| Test | Assertion |
|------|-----------|
| Full uninstall | `~/.wizard/` gone, MCP entries removed from both configs |
| `--yes` skips prompt | No input needed, deletion proceeds |
| Without `--yes` | Prompts for confirmation (mock input) |
| Partial state (some targets missing) | Cleans what exists, skips the rest |
| Nothing to uninstall | Prints message, exits 0 |
| Uninstall after uninstall | `"Nothing to uninstall."` |

---

## 6. Files Changed

| File | Change |
|------|--------|
| `src/wizard/mcp_config.py` | **New** — shared MCP config helpers |
| `src/wizard/cli/main.py` | Add `uninstall` command; add `register_wizard_mcp()` call to `setup` |
| `tests/test_mcp_config.py` | **New** — unit tests for mcp_config |
| `tests/test_cli.py` or existing CLI test file | Integration tests for setup and uninstall |
