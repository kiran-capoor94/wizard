# `wizard verify` — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## `wizard verify`

`wizard verify` is a quick end-to-end health check that confirms Wizard is correctly
installed and the MCP server is reachable. It extends `wizard doctor` by adding an
actual MCP handshake as a final step.

**`wizard verify` vs `wizard doctor`:**

| Command          | Checks                                    | When to use                        |
| ---------------- | ----------------------------------------- | ---------------------------------- |
| `wizard doctor`  | Config, DB, tables, allowlist, agents, migrations, skills, knowledge store | Detailed diagnosis of individual problems |
| `wizard verify`  | Config, DB, tables, skills + **MCP handshake** | After install, after update, when debugging MCP connectivity |

`wizard verify` runs a subset of doctor checks and adds the MCP handshake. It stops at
the first failure and exits with code 1. `wizard doctor` runs all checks (or stops at
first failure depending on flags) and shows a formatted table.

---

## The 5 checks in order

1. **Config file** — `check_config_file()`: confirms `~/.wizard/config.json` (or
   `$WIZARD_CONFIG_FILE`) exists.
2. **DB file** — `check_db_file()`: confirms the SQLite database file exists.
3. **DB tables** — `check_db_tables()`: confirms all required tables are present
   (`task`, `note`, `meeting`, `wizardsession`, `toolcall`, `task_state`, `pseudonym_map`).
4. **Skills installed** — `check_skills_installed()`: confirms at least one agent has
   skills installed, or `~/.wizard/skills/` is populated.
5. **MCP handshake** — `_check_mcp_server()`: starts `wizard-server`, performs an MCP
   handshake, and validates the response.

Checks 1–4 are imported from `wizard.cli.doctor`. Check 5 is defined in `wizard.cli.verify`.

---

## MCP handshake detail

`_check_mcp_server()` performs the following sequence:

1. Starts the server subprocess with `stdin/stdout` pipes, `stderr` discarded.
2. Sends `initialize` (JSON-RPC id=1) with `protocolVersion="2024-11-05"`.
3. Reads the `initialize` response (id=1) before proceeding.
4. Sends `notifications/initialized` (notification, no id).
5. Sends `tools/list` (JSON-RPC id=2).
6. Reads the `tools/list` response (id=2).
7. Sends `shutdown` and closes stdin; waits up to 5 seconds for the process to exit.

**Validation** (`_validate_mcp_responses()`):
- Response id=1 must have `result.serverInfo.name == "wizard"`.
- Response id=2 must have `result.tools` with at least one entry.

On success: `"MCP server starts (N tools registered)"`.
On failure: returns a descriptive message pointing to `wizard doctor`.

The handshake uses interactive pipes (read after each send) to ensure FastMCP flushes
each response before the next request is sent. No tool functions are invoked — `tools/list`
is a server-level operation only.

---

## Command lookup

`_mcp_server_command()` resolves the server binary in this order:

1. `wizard-server` on `PATH` (installed via `uv tool install` or pip). Used if found.
2. `uv --directory <repo_root> run server.py` — dev checkout fallback. `repo_root` is
   resolved as 4 levels up from `verify.py` (`src/wizard/cli/verify.py` → repo root).
3. If neither is found, returns `["wizard-server"]` which will fail with a clear
   `FileNotFoundError`.

---

## Exit behaviour

- Exit code `0` — all 5 checks passed; prints "All checks passed. Wizard is ready."
- Exit code `1` — any check failed; prints the failure message followed by:
  `"Fix: run  wizard doctor  for a detailed diagnosis."`

---

## When to use `wizard verify`

- After `wizard setup` or `uv tool install wizard` — confirms the full stack is wired.
- After `wizard update` — confirms migrations and re-registration didn't break the server.
- When Claude Code shows wizard tools as unavailable — confirms the MCP binary is
  reachable and responding correctly.
- In CI after packaging — smoke-tests the installed entry point.
