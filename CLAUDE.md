# Wizard — Developer Guide

## Coding Principles

Eleven rules that keep the codebase maintainable for a solo engineer:

1. **SLAP (Single Layer of Abstraction)** — each function operates at one
   level. Tool functions orchestrate; they don't build SQL or format API
   payloads.
2. **Unidirectional dependencies** — `tools → services → integrations`
   and `tools → repositories`. Never backwards, never sideways.
3. **Single responsibility (file-scoped)** — each file has one axis of
   change. If you're editing `repositories.py` to fix a Notion API issue,
   something is in the wrong place.
4. **No business logic in integrations** — integration clients are thin
   wrappers (HTTP call, return data, raise on error). Mapping, filtering,
   and scrubbing happen in services or repositories.
5. **DRY at the third occurrence** — don't abstract after two uses. Wait
   for three to confirm it's a real pattern.
6. **Idiomatic `_` prefix** — only use `_` for names that are genuinely
   private to the module or class. If a function is imported by another
   module, it is part of that module's public API and must not have a `_`
   prefix. The `_helpers.py` filename pattern is also discouraged; use
   `helpers.py`.
7. **Classes over function bags** — when multiple functions share state,
   context, or a common pattern (e.g. get session → log → do work),
   group them into a class. Stateless utility functions are fine as
   module-level functions; related stateful behaviour belongs on classes.
8. **No N+1 or N^2** — never call `db.get()` inside a loop. Batch-load
   with `.in_()` queries and build a dict for O(1) lookup. Watch for
   repeated iteration over the same collection — prefer single-pass
   aggregation.
9. **One implementation, many interfaces** — CLI and MCP are interfaces
   to the same domain logic. Both must call the same service methods.
   Never reimplement sync/writeback/query logic in a tool or CLI command
   when a service method already exists.
10. **No ceremony without value** — avoid wrappers that just forward to
    one other function, response types that wrap a single value, or DI
    machinery that adds indirection without enabling testability that
    plain constructor injection couldn't achieve.
11. **No C901, ever** - never suppress or ignore the complexity of a codebase
    file/function/class etc.

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
uv run server.py          # stdio transport — dev use from repo
wizard-server             # installed entry point (after `uv tool install`)
uv run alembic upgrade head   # run pending DB migrations (dev only)
wizard update             # upgrade install + run migrations + re-register agents (installed use)
```

## Project Layout

```text
server.py                    # Entry point — imports mcp_instance, tools, resources, prompts
src/wizard/
  cli/
    main.py                  # Typer app: setup, configure, doctor, analytics, update, uninstall
    serve.py                 # wizard-server entry point (installed MCP binary)
    capture.py               # wizard capture — transcript synthesis trigger (called by hooks)
    configure.py             # configure knowledge-store + synthesis backends subcommands
    doctor.py                # 8-point health checks (wizard doctor)
    analytics.py             # Session/note/task usage stats (wizard analytics)
  mcp_instance.py            # FastMCP app factory; registers ToolLoggingMiddleware + skills
  skills.py                  # Skill loader (reads ~/.wizard/skills/ at startup)
  tools/                       # MCP tools package (split by domain)
    __init__.py                # Re-exports all tool functions
    session_tools.py           # session_start, session_end, resume_session
    session_helpers.py         # build_prior_summaries, find_previous_session_id, mid-session synthesis loop
    task_tools.py              # task_start, save_note, update_task, create_task, rewind_task, what_am_i_missing
    task_fields.py             # apply_task_fields + elicitation helpers (mental model, done confirm, duplicate check)
    formatting.py              # task_contexts_to_json — session response serialisation
    mode_tools.py              # get_modes, set_mode — working mode activation
    triage_tools.py            # what_should_i_work_on (mode-based scoring + LLM reasons)
    meeting_tools.py           # get_meeting, save_meeting_summary, ingest_meeting
    query_tools.py             # get_tasks, get_task, get_sessions, get_session (paginated, no session required)
  repositories/              # Query layer (package)
    task.py                  # TaskRepository
    note.py                  # NoteRepository
    meeting.py               # MeetingRepository
    session.py               # SessionRepository
    task_state.py            # TaskStateRepository
    analytics.py             # AnalyticsRepository — session/note/task usage stats
  resources.py               # 5 read-only MCP resources (wizard://* URIs)
  prompts.py                 # MCP prompt templates
  middleware.py              # ToolLoggingMiddleware — logs tool name on every invocation
  transcript.py              # TranscriptReader (JSONL parser for agent transcripts)
  synthesis.py               # Synthesiser (auto-capture — ordered backend failover)
  llm_adapters.py            # OllamaAdapter + LiteLLM completion wrapper, probe_backend_health, JSON parsing
  mid_session.py             # Background mid-session synthesis state (MID_SESSION_TASKS dict)
  models.py                  # SQLModel ORM: task, note, meeting, wizardsession, toolcall, task_state
  schemas.py                 # Pydantic response types for all MCP tools
  services.py                # SessionCloser — auto-closes abandoned sessions
  security.py                # SecurityService — regex PII scrubbing with allowlist
  config.py                  # Pydantic Settings + BackendConfig + ModesSettings + JsonConfigSettingsSource
  database.py                # SQLite session factory (SQLModel engine)
  deps.py                    # FastMCP Depends() provider functions (incl. get_skill_roots)
  exceptions.py              # ConfigurationError
  agent_registration.py      # Write MCP + hook config into agent JSON/TOML files; refresh_hooks()
  alembic/                   # DB migrations — bundled in package for `wizard update`
  hooks/                     # Hook scripts — bundled in package, copied to ~/.wizard/hooks/ on setup
  skills/                    # FastMCP skills source (copied to ~/.wizard/skills/ by setup)
hooks/                       # Hook scripts source (also bundled as src/wizard/hooks/ for installs)
  session-end.sh             # Claude Code SessionEnd hook — calls `wizard capture --close` to synthesise transcript
  session-start.sh           # Claude Code SessionStart hook — personalization refresh (80%) + session boot injection
alembic/                     # DB migration scripts (dev use; bundled copy lives in src/wizard/alembic/)
tests/
  scenarios/                 # ALL tests live here — scenario/behaviour tests only (no unit tests)
  conftest.py                # shared fixtures
  fakes.py                   # in-memory fakes for repositories
```

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
    "allowed": ["architect", "brainstorm", "product-owner"]
  }
}
```

`knowledge_store.type` is `"notion"`, `"obsidian"`, or `""` (disabled).
Configure interactively with `wizard configure knowledge-store`.
The knowledge store is optional — core Wizard works without it.

## Database Schema

Six SQLite tables via SQLModel:

| Table           | Purpose                                                                                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task`          | Tasks synced from Jira/Notion + local creates. Has `artifact_id` UUID.                                                                                     |
| `note`          | Notes (investigation/decision/docs/learnings/session_summary). Has `artifact_id`, `artifact_type`, `status`, `supersedes_note_id`, `synthesis_confidence`. |
| `meeting`       | Meetings ingested from Krisp or Notion. Has `artifact_id` UUID.                                                                                            |
| `wizardsession` | Session records with serialised SessionState. Has `artifact_id`, `synthesis_status` (`pending`\|`complete`\|`partial_failure`).                            |
| `toolcall`      | Append-only telemetry (tool name + timestamp per session)                                                                                                  |
| `task_state`    | Derived signals (1:1 with task): note counts, stale_days, last_touched                                                                                     |

**Artifact identity (v3):** Every `task`, `meeting`, and `wizardsession` row has a UUID `artifact_id`. Notes carry `artifact_id` + `artifact_type` (`"task"` \| `"session"` \| `"meeting"`) as a single anchor. Attribution priority: task > session > meeting.

**Note lifecycle:** `note.status` is `"active"` by default. Synthesis failures write `"unclassified"` notes with `synthesis_confidence=0.0`. `"superseded"` notes are tracked via `supersedes_note_id`. Analytics and `build_rolling_summary` exclude non-active notes from meaningful counts.

Legacy names: `wizardsession` and `toolcall` predate the snake_case
convention. Don't rename them — they match existing migrations.

New tables use snake_case (e.g. `task_state`, `meeting_tasks`).

## Dependency Injection

`deps.py` provides plain provider functions wired into tools and resources
via FastMCP's `Depends()` system (identical in spirit to FastAPI's):

```python
get_security()             → SecurityService
get_task_repo()            → TaskRepository
get_meeting_repo()         → MeetingRepository
get_note_repo()            → NoteRepository
get_task_state_repo()      → TaskStateRepository
get_session_repo()         → SessionRepository
get_skill_roots()          → list[Path]   # skill search roots for mode tools
```

Tools and resources declare deps as typed default params:

```python
from fastmcp.dependencies import Depends
from .deps import get_task_repo
from .repositories import TaskRepository

async def my_tool(
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
) -> ...:
    ...
```

FastMCP resolves and caches providers per-request; injected params are
hidden from the LLM-visible tool schema. Provider functions are plain
callables — no `Depends()` in their own signatures — so CLI code can call
them directly without FastMCP.

In tests: call tool/resource functions with deps as explicit kwargs
(FastMCP is not involved when calling directly):

```python
result = await my_tool(task_id=1, t_repo=TaskRepository())
```

## Doctor Checks

`wizard doctor` runs 8 checks in order. Stops at first failure unless
`--all` is passed.

| #   | Check             | What it validates                             |
| --- | ----------------- | --------------------------------------------- |
| 1   | DB file           | `settings.db` path exists                     |
| 2   | Config file       | `~/.wizard/config.json` exists                |
| 3   | DB tables         | All 6 required tables present                 |
| 4   | Allowlist file    | `~/.wizard/allowlist.txt` exists              |
| 5   | Agent registered  | ≥1 agent in registered_agents.json or scanned |
| 6   | Migration current | Alembic revision matches DB                   |
| 7   | Skills installed  | `~/.wizard/skills/` is non-empty              |
| 8   | Knowledge store   | KS type configured (INFO only)                |

## Agent Registration

`wizard setup --agent <agent>` writes MCP config into the agent's config
file **and** installs the auto-capture SessionEnd hook into the agent's
global hooks config. Supported agents and their config locations:

| Agent            | MCP Config                                                        | Hook Config               | Hook Event               |
| ---------------- | ----------------------------------------------------------------- | ------------------------- | ------------------------ |
| `claude-code`    | `~/.claude.json`                                                  | `~/.claude/settings.json` | SessionEnd, SessionStart |
| `claude-desktop` | `~/Library/Application Support/Claude/claude_desktop_config.json` | _(no hooks)_              | —                        |
| `gemini`         | `~/.gemini/settings.json`                                         | `~/.gemini/settings.json` | SessionEnd               |
| `opencode`       | `~/.config/opencode/opencode.json`                                | _(TypeScript plugin)_     | —                        |
| `codex`          | `~/.codex/config.toml`                                            | `~/.codex/hooks.json`     | Stop                     |
| `copilot`        | `~/.copilot/mcp-config.json`                                      | `~/.copilot/config.json`  | sessionEnd               |

`wizard setup --agent all` registers all six (MCP) and installs hooks
where supported. `wizard update` re-registers both. `wizard uninstall`
removes both.

MCP entry point:

```json
{
  "command": "wizard-server",
  "args": [],
  "type": "stdio"
}
```

## Session Continuity Tracking

Wizard tracks three distinct session layers and links them explicitly:

| Layer                     | ID type                    | Lifetime                   | Stored in                        |
| ------------------------- | -------------------------- | -------------------------- | -------------------------------- |
| Claude Code agent session | UUID string                | Single conversation thread | `WizardSession.agent_session_id` |
| Wizard session            | Integer (SQLite PK)        | Matches agent session 1:1  | `WizardSession.id`               |
| FastMCP session           | Per-connection `ctx.state` | Transport lifetime         | Not persisted                    |

**Session directory (`~/.wizard/sessions/<uuid>/`):**

Each top-level agent session owns an isolated directory. Sub-agents have no directory (they're suppressed entirely).

| File        | Written by                              | Read by                             | Content                                 |
| ----------- | --------------------------------------- | ----------------------------------- | --------------------------------------- |
| `source`    | `session-start.sh` hook at SessionStart | `session_start` tool                | `"startup"`, `"compact"`, or `"resume"` |
| `wizard_id` | `session_start` tool after DB insert    | `session-end.sh` hook at SessionEnd | Integer wizard session ID               |

The directory is deleted by `session-end.sh` after `wizard capture` completes.

**Sub-agent suppression:**

Both `session-start.sh` and `session-end.sh` exit immediately (`exit 0`) when `agent_id` is present in the hook payload. Top-level sessions never have `agent_id` — this is the suppression signal from Claude Code.

**Continuation detection (`session_start` tool):**

1. The `SessionStart` hook writes `source` (from payload) to `~/.wizard/sessions/<uuid>/source`.
2. The hook emits `agent_session_id=<uuid> source=<source>` in `additionalContext`.
3. The agent calls `session_start(agent_session_id=<uuid>)`.
4. `session_start` reads `source` from the keyed directory.
5. If `source == "compact"`, the tool queries the DB for the most recent prior session and sets `continued_from_id`.

**Key files:**

- `hooks/session-start.sh` — sub-agent suppression, keyed dir write, UUID in additionalContext
- `hooks/session-end.sh` — sub-agent suppression, keyed dir lookup, cleanup
- `tools/session_tools.py` — `SESSIONS_DIR`, `_find_previous_session_id`, `agent_session_id` param
- `models.py` — `WizardSession.agent_session_id`, `WizardSession.continued_from_id`
- `schemas.py` — `SessionStartResponse.source`, `SessionStartResponse.continued_from_id`

## Auto-Capture (Transcript Synthesis)

Wizard automatically generates structured notes from agent conversation
transcripts. This removes the need for manual `save_note` calls — tasks
accumulate context as you work.

**How it works:**

1. A **SessionEnd hook** fires when the agent's session ends (installed by
   `wizard setup`).
2. The hook calls `wizard capture --close --transcript <path> --agent <id> --agent-session-id <uuid>`.
3. `wizard capture` finds the wizard session matching `--session-id` (written
   by `session_start`) or the most recent unsynthesised session within 24h,
   sets `transcript_path`, `agent`, and `agent_session_id`, then calls
   `Synthesiser` which routes to `OllamaAdapter` (native `/api/chat`, no
   grammar constraint, `think:false`) for Ollama backends, or to LiteLLM for
   cloud providers, and saves the resulting notes to SQLite.
   On success, `WizardSession.is_synthesised` is set to `True`.
   Raw transcript JSONL is persisted to `wizardsession.transcript_raw` before
   synthesis so re-synthesis remains possible after the agent deletes the file.

**Synthesis is fully decoupled from the MCP server.** It runs at hook time,
before the next session starts. No `ctx.sample()` involved — no round-trip
cost, no dependency on MCP context availability.

**Fallback:** If the LLM server is unreachable, `wizard capture` exits non-zero.
The session retains its `transcript_path` (`is_synthesised` stays `False`). Retry
with `wizard capture --close --session-id <id>` when the server is available.

**Key files:**

- `transcript.py` — `TranscriptReader` (JSONL parser)
- `synthesis.py` — `Synthesiser` (backend selection + note persistence)
- `llm_adapters.py` — `OllamaAdapter`, `complete()` (LiteLLM call), `probe_backend_health()`, JSON parsing
- `hooks/session-end.sh` — Claude Code hook script
- `agent_registration.py` — `register_hook()` / `deregister_hook()`
- `config.py` — `SynthesisSettings` + `BackendConfig` (ordered backends list)

**`WIZARD_AGENT` environment variable:** `session-end.sh` uses this to
identify the agent type when building the `wizard capture` command. It is
set in the hook command registered by `register_hook()` at setup time
(e.g. `WIZARD_AGENT=gemini bash /path/to/session-end.sh`). Valid values
match `TranscriptReader._PARSERS`: `claude-code`, `codex`, `gemini`,
`opencode`, `copilot`. Defaults to `claude-code` if unset.

**Transcript format:** Claude Code writes JSONL with `type` field
(`user`, `assistant`, `progress`, `file-history-snapshot`, `system`,
`last-prompt`). The reader skips noise types and normalises
`tool_use`/`tool_result` blocks into `TranscriptEntry` objects.

**Task matching:** `Synthesiser` always sets `task_id=None` on notes.
Wizard owns task matching — the LLM is not shown the task list.

**Limitations:**

- No mid-session intelligence — synthesis runs at session boundaries only
- Transcript file must exist at synthesis time; if deleted, falls back to `wizardsession.transcript_raw` (persisted at capture time)
- Parsers: Claude Code (full), Codex, Gemini, OpenCode, Copilot CLI
- Ollama backends require a running Ollama server; cloud backends require a valid API key

## Session Personalization

Wizard refreshes Claude Code's appearance and auto-boots the session skill
on every `SessionStart` event.

**How it works:**

1. A **SessionStart hook** (`hooks/session-start.sh`) fires at the start of
   every Claude Code session (installed by `wizard setup`).
2. **80% probability gate** (`$((RANDOM % 10)) -lt 8`): a Python heredoc
   queries `wizard.db`, selects an announcement based on task signals, picks
   a spinner verb pack, samples tips, and merges them into
   `~/.claude/settings.json`. Keys written: `companyAnnouncements`,
   `spinnerVerbs`, `spinnerTipsOverride`, and `statusLine` (only if absent).
3. **Always**: outputs `additionalContext` JSON instructing the agent to
   call the `wizard:session_start` MCP tool — no manual trigger needed.

**Announcement priority** (first match wins):

- Overdue tasks
- Analysis loops (`note_count > 3 and decision_count = 0`)
- Stale tasks (untouched > 14 days)
- Open task count > 20
- Generic fallback

**Spinner packs** — three themed sets (Absurdist, Stoic, Dramatic) selected
randomly each session.

**Failure isolation:** the personalization block runs with `|| true` — a
SQLite error or missing config file never blocks the session boot injection.

**Key files:**

- `hooks/session-start.sh` — hook script (bash + python3 heredoc)
- `agent_registration.py` — `register_hook()` / `deregister_hook()` now
  iterate `_HOOK_SCRIPTS` to install both SessionEnd and SessionStart

## MCP Tools — Quick Reference

| Tool                    | Key inputs                                                                                      | Key outputs                                                                                                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `session_start`         | agent_session_id?                                                                               | session_id, source, continued_from_id, open_tasks, open_tasks_total, blocked_tasks, unsummarised_meetings, wizard_context, closed_sessions, active_mode, available_modes |
| `session_end`           | session_id, summary, intent, working_set, state_delta, open_loops, next_actions, closure_status | note_id, session_state_saved                                                                                                               |
| `resume_session`        | session_id?                                                                                     | session_id, resumed_from, session_state, working_set_tasks, prior_notes                                                                    |
| `task_start`            | task_id                                                                                         | task, notes_by_type, prior_notes, latest_mental_model, compounding                                                                         |
| `create_task`           | name, priority, category, source_url?, meeting_id?                                              | task_id, already_existed                                                                                                                   |
| `update_task`           | task_id + optional fields                                                                       | updated_fields                                                                                                                             |
| `rewind_task`           | task_id                                                                                         | task, timeline (oldest→newest), summary                                                                                                    |
| `save_note`             | task_id, note_type, content, mental_model?                                                      | note_id, mental_model_saved                                                                                                                |
| `what_am_i_missing`     | task_id                                                                                         | list of Signal(type, severity, message)                                                                                                    |
| `what_should_i_work_on` | session_id, mode, time_budget?                                                                  | recommended_task, alternatives, skipped_blocked                                                                                            |
| `get_modes`             | session_id?                                                                                     | available_modes, active_mode                                                                                                               |
| `set_mode`              | session_id, mode_name                                                                           | active_mode, description, instruction                                                                                                      |
| `get_meeting`           | meeting_id                                                                                      | title, content, open_tasks, already_summarised                                                                                             |
| `save_meeting_summary`  | meeting_id, summary, task_ids?                                                                  | note_id, tasks_linked                                                                                                                      |
| `ingest_meeting`        | title, content, source_url?, category?                                                          | meeting_id, already_existed                                                                                                                |
| `get_tasks`             | status?, source_type?, limit, cursor?                                                           | items, next_cursor, total                                                                                                                  |
| `get_task`              | task_id                                                                                         | task, notes, task_state                                                                                                                    |
| `get_sessions`          | limit, cursor?                                                                                  | items, next_cursor                                                                                                                         |
| `get_session`           | session_id                                                                                      | session, state, notes                                                                                                                      |

## PII Scrubbing

`SecurityService` scrubs content before it touches SQLite. Six patterns:

| Pattern     | Example match      | Replacement     |
| ----------- | ------------------ | --------------- |
| NHS ID      | `123 456 7890`     | `[NHS_ID_1]`    |
| NI Number   | `AB123456C`        | `[NI_NUMBER_1]` |
| Email       | `user@example.com` | `[EMAIL_1]`     |
| UK Phone    | `+44 7700 900000`  | `[PHONE_1]`     |
| UK Postcode | `SW1A 1AA`         | `[POSTCODE_1]`  |
| Secrets     | `Bearer sk-...`    | `[SECRET_1]`    |

Configure `scrubbing.allowlist` with regex patterns for identifiers that
should pass through unchanged (e.g. `"ENG-\\d+"` preserves Jira keys).

## Key Invariants

- Scrub PII **before** writing to SQLite, not on read.
- `session_start` must be called before `task_start` or `save_note`.
- `update_task_status` is deprecated; always use `update_task`.

## File Size & Structural Thresholds

Hard caps enforced by `scripts/pre-commit`:

| Scope                    | Cap       | Enforcement                   |
| ------------------------ | --------- | ----------------------------- |
| Any `src/wizard/**/*.py` | 500 lines | Pre-commit hook blocks commit |
| Any `tests/**/*.py`      | 500 lines | Pre-commit hook blocks commit |
| Tools per file           | 10        | Split trigger (manual)        |

Structural split triggers:

| Trigger                             | Action                             |
| ----------------------------------- | ---------------------------------- |
| `integrations.py` adds a 3rd client | Split into `integrations/` package |
| `repositories.py` adds a 5th repo   | Split into `repositories/` package |
| Any test file exceeds 500 lines     | Split into `tests/test_<module>/`  |

## Pre-Commit Hook

`scripts/pre-commit` runs three checks:

1. **Line count** — blocks files over 500 lines in `src/wizard/` and
   `tests/`.
2. **Import boundaries** — blocks cross-layer imports (repos importing
   integrations, integrations importing tools, etc.).
3. **Ruff** — runs `ruff check` on staged files.

Install: `ln -sf ../../scripts/pre-commit .git/hooks/pre-commit`

**Near-cap files:** `tools/session_tools.py` (~390 lines) is approaching the cap. `tools/task_tools.py` was split — elicitation helpers moved to `task_fields.py` (now ~469 lines).
