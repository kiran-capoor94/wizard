# Wizard — Developer Guide

## Running Tests

Always run via `uv run` — plain `python` resolves to system Python and
won't see the project's virtualenv dependencies:

```bash
uv run pytest                        # full suite
uv run pytest tests/test_tools.py    # single file
uv run pytest -k "test_sync"         # by name pattern
uv run pytest -q                     # quiet output
```

**Do not** use `python -m pytest` directly — `tomli_w` and other
dependencies live in the uv venv, not the system Python.

## Running the Server

```bash
uv run server.py          # stdio transport (as used by MCP clients)
uv run alembic upgrade head   # run pending DB migrations
```

## Project Layout

```text
server.py                    # Entry point — imports mcp_instance, tools, resources, prompts
src/wizard/
  cli/
    main.py                  # Typer app: setup, configure, sync, doctor, analytics, update, uninstall
    doctor.py                # 10-point health checks (wizard doctor)
    analytics.py             # Session/note/task usage stats (wizard analytics)
  mcp_instance.py            # FastMCP app factory; registers ToolLoggingMiddleware + skills
  tools.py                   # 13 MCP tools (all async, all return Pydantic schemas)
  resources.py               # 5 read-only MCP resources (wizard://* URIs)
  prompts.py                 # MCP prompt templates
  middleware.py              # ToolLoggingMiddleware — logs tool name on every invocation
  models.py                  # SQLModel ORM: task, note, meeting, wizardsession, toolcall, task_state
  schemas.py                 # Pydantic response types for all MCP tools
  repositories.py            # Query layer over SQLite (TaskRepo, NoteRepo, MeetingRepo, etc.)
  services.py                # SyncService (bidirectional upsert) + WriteBackService
  integrations.py            # JiraClient (httpx) + NotionClient (notion-client v3.0)
  notion_discovery.py        # 3-pass Notion property auto-matching for wizard configure --notion
  security.py                # SecurityService — regex PII scrubbing with allowlist
  config.py                  # Pydantic Settings + JsonConfigSettingsSource
  mappers.py                 # Jira/Notion → TaskStatus/TaskPriority/MeetingCategory
  database.py                # SQLite session factory (SQLModel engine)
  deps.py                    # @lru_cache dependency singletons
  agent_registration.py      # Write MCP config into agent JSON/TOML files
  skills/                    # FastMCP skills source (copied to ~/.wizard/skills/ by setup)
alembic/                     # DB migration scripts
tests/                       # pytest suite
```

## Configuration Schema

Config file: `~/.wizard/config.json` (override: `WIZARD_CONFIG_FILE` env var)

```json
{
  "name": "wizard",
  "version": "1.1.6",
  "db": "~/.wizard/wizard.db",
  "jira": {
    "base_url": "",
    "project_key": "",
    "token": "",
    "email": ""
  },
  "notion": {
    "token": "",
    "sisu_work_page_id": "",
    "tasks_ds_id": "",
    "meetings_ds_id": ""
  },
  "scrubbing": {
    "enabled": true,
    "allowlist": []
  }
}
```

**Critical:** `tasks_ds_id` and `meetings_ds_id` are Notion **data source
IDs**, not database page IDs. These are distinct — page IDs appear in
Notion URLs; data source IDs are surfaced by the Notion API's
`data_sources` field on a `databases.retrieve` response. The
`notion_discovery` module and `wizard configure --notion` use the data
source IDs directly.

The `notion_schema` block is auto-populated by `wizard configure --notion`
and maps wizard field names to actual Notion property names:

```json
"notion_schema": {
  "task_name": "Task",
  "task_status": "Status",
  "task_priority": "Priority",
  "task_due_date": "Due date",
  "task_jira_key": "Jira",
  "meeting_title": "Meeting name",
  "meeting_category": "Category",
  "meeting_date": "Date",
  "meeting_url": "Krisp URL",
  "meeting_summary": "Summary"
}
```

## Notion API — Use `data_sources`, Not `databases`

Wizard uses **notion-client v3.0** which exposes both the legacy
`databases.*` endpoint and the new `data_sources.*` endpoint.

**Always use `data_sources.*`:**

| Operation | Call |
|-----------|------|
| Fetch schema | `client.data_sources.retrieve(data_source_id=ds_id)` |
| Query rows | `client.data_sources.query(data_source_id=ds_id, ...)` |
| Create page in DB | `client.pages.create(parent={"data_source_id": ds_id}, ...)` |

**Never use:**
- `client.databases.retrieve()` — returns empty `properties` for
  multi-source databases (the new default in Notion)
- `client.databases.query()` — removed in notion-client v3.0
- `parent={"database_id": ...}` in `pages.create` — rejects data source
  IDs with 404

The config stores data source IDs specifically because all three operations
above require them. No lookup or translation is needed at call time.

## Database Schema

Six SQLite tables via SQLModel:

| Table | Purpose |
|-------|---------|
| `task` | Tasks synced from Jira/Notion + local creates |
| `note` | Notes (investigation/decision/docs/learnings/session_summary) |
| `meeting` | Meetings ingested from Krisp or Notion |
| `wizardsession` | Session records with serialised SessionState |
| `toolcall` | Append-only telemetry (tool name + timestamp per session) |
| `task_state` | Derived signals (1:1 with task): note counts, stale_days, last_touched |

Legacy names: `wizardsession` and `toolcall` predate the snake_case
convention. Don't rename them — they match existing migrations.

New tables use snake_case (e.g. `task_state`, `meeting_tasks`).

## Dependency Injection

`deps.py` uses `@lru_cache` singletons — one instance per process:

```python
jira_client()       → JiraClient
notion_client()     → NotionClient
security()          → SecurityService
sync_service()      → SyncService
writeback()         → WriteBackService
task_repo()         → TaskRepository
meeting_repo()      → MeetingRepository
note_repo()         → NoteRepository
task_state_repo()   → TaskStateRepository
```

In tests: call `<func>.cache_clear()` to reset between test cases.
Config changes require a process restart (cache is process-scoped).

## Test Patterns

Model/schema imports must be **inside test function bodies**, not at
module level. The `db_session` fixture clears `sys.modules` between
tests, which causes `UnmappedClassError` for module-level imports.

```python
# Correct
def test_something(db_session):
    from wizard.models import Task
    task = Task(...)

# Wrong — causes UnmappedClassError
from wizard.models import Task
def test_something(db_session):
    task = Task(...)
```

## Doctor Checks

`wizard doctor` runs 10 checks in order. Stops at first failure unless
`--all` is passed. Check 8 (Notion schema) is skipped if check 2
(Notion token) fails.

| # | Check | What it validates |
|---|-------|------------------|
| 1 | DB file | `settings.db` path exists |
| 2 | Notion token | `notion.token` is set |
| 3 | Jira token | `jira.token` is set |
| 4 | Config file | `~/.wizard/config.json` exists |
| 5 | DB tables | All 6 required tables present |
| 6 | Allowlist file | `~/.wizard/allowlist.txt` exists |
| 7 | Agent registered | ≥1 agent in registered_agents.json or scanned |
| 8 | Notion schema | Live DB properties match config schema (skipped if no token) |
| 9 | Migration current | Alembic revision matches DB |
| 10 | Skills installed | `~/.wizard/skills/` is non-empty |

## Agent Registration

`wizard setup --agent <agent>` writes MCP config into the agent's config
file. Supported agents and their config locations:

| Agent | Config file | Format |
|-------|------------|--------|
| `claude-code` | `~/.claude/claude_code_config.json` | JSON (`mcpServers`) |
| `claude-desktop` | `~/Library/Application Support/Claude/claude_desktop_config.json` | JSON (`mcpServers`) |
| `gemini` | `~/.gemini/settings.json` | JSON (`mcpServers`) |
| `opencode` | `~/.config/opencode/config.json` | JSON (`mcp`) |
| `codex` | `~/.codex/config.toml` | TOML (`mcpServers`) |

`wizard setup --agent all` registers all five. MCP entry point:

```json
{
  "command": "uv",
  "args": ["--directory", "<repo-path>", "run", "server.py"]
}
```

## MCP Tools — Quick Reference

13 tools, all async, all return Pydantic response schemas:

| Tool | Key inputs | Key outputs |
|------|-----------|------------|
| `session_start` | — | session_id, open_tasks, blocked_tasks, unsummarised_meetings |
| `session_end` | session_id, summary, intent, working_set, state_delta, open_loops, next_actions, closure_status | note_id, notion_write_back, session_state_saved |
| `resume_session` | session_id? | session_id, resumed_from, session_state, working_set_tasks, prior_notes |
| `task_start` | task_id | task, notes_by_type, prior_notes, latest_mental_model, compounding |
| `create_task` | name, priority, category, source_url?, meeting_id? | task_id, notion_write_back |
| `update_task` | task_id + optional fields | updated_fields, writebacks |
| `rewind_task` | task_id | task, timeline (oldest→newest), summary |
| `save_note` | task_id, note_type, content, mental_model? | note_id, mental_model_saved |
| `what_am_i_missing` | task_id | list of Signal(type, severity, message) |
| `get_meeting` | meeting_id | title, content, open_tasks, already_summarised |
| `save_meeting_summary` | meeting_id, summary, task_ids? | note_id, tasks_linked, notion_write_back |
| `ingest_meeting` | title, content, source_url?, category? | meeting_id, already_existed, notion_write_back |
| `update_task_status` | task_id, new_status | _(deprecated — use update_task)_ |

## PII Scrubbing

`SecurityService` scrubs content before it touches SQLite. Six patterns:

| Pattern | Example match | Replacement |
|---------|--------------|-------------|
| NHS ID | `123 456 7890` | `[NHS_ID_1]` |
| NI Number | `AB123456C` | `[NI_NUMBER_1]` |
| Email | `user@example.com` | `[EMAIL_1]` |
| UK Phone | `+44 7700 900000` | `[PHONE_1]` |
| UK Postcode | `SW1A 1AA` | `[POSTCODE_1]` |
| Secrets | `Bearer sk-...` | `[SECRET_1]` |

Configure `scrubbing.allowlist` with regex patterns for identifiers that
should pass through unchanged (e.g. `"ENG-\\d+"` preserves Jira keys).

## Sync Rules

External sources (Jira/Notion) win on metadata; local wins on status:

- **Jira/Notion overwrite:** name, priority, due_date
- **Local preserved:** status (a deliberate BLOCKED shouldn't be undone by sync)
- **Dedup order:** Jira key → Notion notion_id → source_id

## Key Invariants

- Scrub PII **before** writing to SQLite, not on read.
- `session_start` must be called before `task_start` or `save_note`.
- `update_task_status` is deprecated; always use `update_task`.
- `tasks_ds_id` / `meetings_ds_id` are data source IDs. Never store page
  IDs in those fields or the Notion API calls will 404.
- Never call `databases.retrieve` or `databases.query` — these are legacy
  endpoints that don't work with multi-source Notion databases.
