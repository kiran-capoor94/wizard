# CLI Reference

Entry point: `wizard` (typer app in `src/wizard/cli/main.py`)

---

## `wizard setup`

**Entry point:** `setup()` in `src/wizard/cli/main.py`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--agent` | `str \| None` | `None` | Agent to register: `claude-code`, `claude-desktop`, `gemini`, `opencode`, `codex`, `copilot`, `all`. Prompted interactively if omitted. |

**Steps:**
1. `ensure_wizard_home()` — creates `~/.wizard/` if absent
2. `initialize_config()` — writes `~/.wizard/config.json` with defaults (no-op if exists)
3. `initialize_allowlist()` — creates `~/.wizard/allowlist.txt` (no-op if exists)
4. `ensure_editable_pth()` — clears `UF_HIDDEN` macOS flag on editable `.pth` (dev installs only)
5. `refresh_hooks()` — syncs hook scripts from package into `~/.wizard/hooks/`
6. `refresh_skills()` — copies `src/wizard/skills/` into `~/.wizard/skills/`
7. Checks DB health via `db_is_healthy()`; if unhealthy, runs `run_migrations()`
8. Prompts for agent (if `--agent` omitted), calls `_reg_service.register_agents()`
9. Writes `~/.wizard/registered_agents.json` with successfully registered agent IDs
10. Prints success panel with next steps

**Exit codes:** `0` success; `1` if DB migration fails

---

## `wizard uninstall`

**Entry point:** `uninstall()` in `src/wizard/cli/main.py`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--yes` | `bool` | `False` | Skip confirmation prompt |

**Steps:**
1. Reads `~/.wizard/registered_agents.json`; falls back to scanning all agent config files
2. Builds a manifest of files to delete: `wizard.db`, `config.json`, `skills/`
3. Displays deletion panel and prompts confirmation (skipped with `--yes`)
4. Calls `deregister_agents()` — removes MCP entry, hooks, and skills for each agent
5. Calls `uninstall_wizard()` — deletes `~/.wizard/` directory tree
6. Prints advisory to run `uv pip uninstall wizard` to remove the package

**Exit codes:** `0` always (aborts print "Aborted." on denial)

---

## `wizard doctor`

**Entry point:** `doctor()` in `src/wizard/cli/doctor.py`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--all` | `bool` | `False` | Report all failures instead of stopping at first |

**All 8 checks (in order):**

| # | Name | What it tests | Fail behaviour |
|---|------|---------------|----------------|
| 1 | DB file exists | `WIZARD_DB` env or `settings.db` path exists on disk | FAIL: "Database not found … run 'wizard setup'" |
| 2 | Config file | `~/.wizard/config.json` (or `WIZARD_CONFIG_FILE` env) exists | FAIL: "Config file not found" |
| 3 | DB tables | All 7 required tables present: `task`, `note`, `meeting`, `wizardsession`, `toolcall`, `task_state`, `pseudonym_map` | FAIL: lists missing table names |
| 4 | Allowlist file | `~/.wizard/allowlist.txt` exists | **PASS** even if absent (advisory only — "run 'wizard setup' to create it") |
| 5 | Agent registered | `~/.wizard/registered_agents.json` non-empty, or at least one agent config contains `wizard` key | FAIL: "No agents registered" |
| 6 | Migration current | Alembic revision matches current head via `MigrationContext.get_current_revision()` | FAIL: "Migration check failed" |
| 7 | Skills installed | Wizard skill files present in any registered agent's skills dir, or `~/.wizard/skills/` non-empty | FAIL: "Skills not installed" |
| 8 | Knowledge store | `settings.knowledge_store.type` set | **PASS** even if empty (advisory: "session summaries saved locally only") |

**Behaviour:**
- Without `--all`: stops at first failure
- With `--all`: runs all checks, reports each
- Exits `1` if any check failed; `0` if all pass

---

## `wizard verify`

**Entry point:** `verify()` in `src/wizard/cli/verify.py`

No flags.

**5 steps in order:**
1. `check_config_file()` — config exists
2. `check_db_file()` — DB file exists
3. `check_db_tables()` — all required tables present
4. `check_skills_installed()` — skills present
5. `_check_mcp_server()` — MCP handshake (see below)

**MCP handshake details:**
- Launches `wizard-server` (prefers installed entry point; falls back to `uv run server.py` from repo root)
- Sends JSON-RPC `initialize` (protocol `2024-11-05`, clientInfo `wizard-verify/1.0`)
- Reads `initialize` response, verifies `serverInfo.name == "wizard"`
- Sends `notifications/initialized`, then `tools/list`
- Reads `tools/list` response, verifies `result.tools` present
- Sends `shutdown`, closes stdin, waits up to 5s
- Reports count of registered tools on success

**Exit codes:** `1` on any step failure; `0` on success

---

## `wizard capture`

**Entry point:** `capture()` in `src/wizard/cli/capture.py`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--close` | `bool` | `False` | Required for operation; any other mode prints "Only --close mode is supported." and exits 0 |
| `--transcript` | `str` | `""` | Path to transcript file |
| `--agent` | `str` | `""` | Agent name (e.g. `claude-code`) |
| `--session-id` | `int \| None` | `None` | Wizard DB session ID; if omitted, finds latest unsynthesised session within 24h |
| `--agent-session-id` | `str \| None` | `None` | Agent-assigned session UUID (stored on session row) |

**Steps:**
1. **Guard:** exits `0` if `--close` not given
2. Transaction 1 (metadata): finds target session → stamps `transcript_path`, `agent`, `agent_session_id`, `closed_by="hook"`; reads raw transcript into `session.transcript_raw` if not already stored; collects transcript paths; builds task table
3. If `settings.synthesis.enabled` is False: marks `synthesis_status="complete"` and exits
4. If no transcript paths: marks `synthesis_status="complete"` and exits
5. LLM synthesis phase (DB unlocked): `Synthesiser.generate_notes()` per transcript path
6. Transaction 2 (persistence): `Synthesiser.persist()` writes notes; sets `is_synthesised=True`, `synthesis_status="complete"`
7. On LLM failure: writes failure marker note, sets `synthesis_status="partial_failure"`, exits `1`

**Exit codes:** `0` success or skipped; `1` LLM synthesis failure

---

## `wizard configure synthesis`

**Entry point:** `synthesis_list()` callback + subcommands in `src/wizard/cli/configure.py`

Sub-commands:

### `wizard configure synthesis` (no subcommand)
Lists all configured LLM backends (description, model, base URL). Tried in order — first healthy backend wins.

### `wizard configure synthesis add`
| Option | Prompt | Description |
|--------|--------|-------------|
| `--model` | "Model (e.g. ollama/gemma4:latest-64k)" | LiteLLM model string |
| `--base-url` | "Base URL (blank for cloud APIs)" | Local server URL |
| `--api-key` | "API key" (hidden) | API key |
| `--description` | "Description" | Human label |

Appends to `synthesis.backends` array in `~/.wizard/config.json`.

### `wizard configure synthesis remove <index>`
Removes backend by 1-based index number.

### `wizard configure synthesis move <from_pos> <to_pos>`
Reorders backends. Position 1 = highest priority (tried first).

### `wizard configure synthesis test [<index>]`
Probes backend reachability via `probe_backend_health()`. Local servers are probed; cloud APIs always pass. Omit index to test all.

---

## `wizard configure knowledge-store`

**Entry point:** `configure_knowledge_store()` in `src/wizard/cli/main.py`

**Interactive prompts:**

1. Knowledge store type: `notion` | `obsidian` | `none`

If `notion`:
- Notion daily page parent ID
- Notion tasks DB ID (optional)
- Notion meetings DB ID (optional)

If `obsidian`:
- Obsidian vault path
- Daily notes folder (default: `Daily`)
- Tasks folder (default: `Tasks`)

Writes `knowledge_store` key into `~/.wizard/config.json`.

---

## `wizard analytics`

**Entry point:** `analytics()` in `src/wizard/cli/main.py`

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--day` | `bool` | `False` | Show today's analytics |
| `--week` | `bool` | `False` | Show last 7 days (default when no flag given) |
| `--month` | `bool` | `False` | Show last 30 days |
| `--from` | `str \| None` | `None` | Start date `YYYY-MM-DD` |
| `--to` | `str \| None` | `None` | End date `YYYY-MM-DD` |

**Note:** `--day`, `--week`, `--month`, `--from`/`--to` are mutually exclusive. Default (no flag) = last 365 days.

**Output:** 3-column Rich table: Sessions | Notes | Tasks, plus health advisory messages.

**Exit codes:** `1` if DB not found or mutually exclusive flags; `0` otherwise

---

## `wizard dashboard`

**Entry point:** `dashboard()` in `src/wizard/cli/main.py`

No flags.

Launches `wizard/cli/dashboard.py` via Streamlit (`streamlit run`). Uses `sys.executable`'s sibling `streamlit` binary. Exits with Streamlit's return code.

---

## `wizard update`

**Entry point:** `update()` in `src/wizard/cli/main.py`

No flags.

**Steps:**
1. Reads `~/.wizard/registered_agents.json`; falls back to scanning config files
2. Deregisters currently registered agents (removes old skills/hooks)
3. **Dev install** (`is_editable_install()` → True):
   - `git pull` in repo root
   - `uv sync` (or `pip install -e` if uv not found)
   - `ensure_editable_pth()`
4. **Installed** (`is_editable_install()` → False):
   - `uv tool upgrade wizard`
5. Runs DB migrations via `run_migrations()`
6. `refresh_hooks()` — syncs hook scripts from newly installed package
7. `refresh_skills()` — copies new skill sources into `~/.wizard/skills/`
8. Re-registers previously registered agents with new skills/hooks

**Exit codes:** `1` if any step fails; `0` on success

---

## `wizard serve`

**Entry point:** `src/wizard/cli/serve.py` (also `server.py` at repo root)

Starts the FastMCP server on stdio transport. Registered as `wizard-server` entry point.
