# Architecture — AI Fact Sheet

## Layer Rules

- Dependency direction: `tools → services → integrations` and `tools → repositories`
- **Never backwards. Never sideways.**
- Integrations are thin HTTP wrappers only — no mapping, filtering, or scrubbing
- Services and repositories own all domain logic
- CLI and MCP are interfaces to the same service methods — never reimplement logic in tools or CLI commands

## File Layout

### `src/wizard/*.py`

| File | Description |
|------|-------------|
| `__init__.py` | Package marker (empty) |
| `agent_registration.py` | Registers wizard as an MCP server in agent config files (Claude, Codex, etc.) |
| `config.py` | `Settings` object (pydantic-settings); reads env vars and `~/.wizard/config.toml` |
| `database.py` | SQLite engine creation, session factory, and `get_session` generator |
| `deps.py` | FastMCP `Depends()` provider functions for repository injection |
| `exceptions.py` | `ConfigurationError` — raised on missing/invalid wizard config |
| `llm_adapters.py` | LiteLLM completion wrappers for synthesis backend |
| `mcp_instance.py` | Creates the top-level `FastMCP` instance with middleware and skills provider |
| `mid_session.py` | Background asyncio task registry for mid-session synthesis |
| `middleware.py` | `SessionStateMiddleware` (session hydration) and `ToolLoggingMiddleware` (telemetry) |
| `models.py` | All SQLModel table definitions and enums |
| `prompts.py` | MCP prompts (skills exposed as `/` slash commands) |
| `resources.py` | MCP resources (read-only config/task data exposed as resource URIs) |
| `schemas.py` | Pydantic request/response schemas and `SessionState` |
| `security.py` | PII scrubbing via regex + phonenumbers; pseudonymisation helpers |
| `services.py` | Orchestration layer — all domain write operations callable from both tools and CLI |
| `skills.py` | Loads skill YAML from `src/wizard/alembic/skills/` directory |
| `synthesis.py` | `Synthesiser` class — converts agent transcripts into `Note` objects via LLM |
| `synthesis_prompt.py` | Stateless prompt-formatting helpers extracted from `synthesis.py` |
| `transcript.py` | Reads and normalises agent conversation transcripts (JSONL) |

### `src/wizard/cli/*.py`

| File | Description |
|------|-------------|
| `__init__.py` | Package marker (empty) |
| `analytics.py` | `wizard analytics` command — Rich tables for session/note/task stats |
| `capture.py` | `wizard capture` command — triggers transcript synthesis into notes |
| `configure.py` | `wizard configure` command — interactive setup of Notion/Jira credentials |
| `dashboard.py` | `wizard dashboard` command — launches Streamlit health dashboard |
| `doctor.py` | `wizard doctor` command — runs self-checks (DB version, config, connectivity) |
| `main.py` | Root Typer app; registers all sub-commands; `wizard` entry point |
| `serve.py` | `wizard-server` entry point — starts MCP server on stdio transport |
| `verify.py` | `wizard verify` command — confirms MCP installation is working |

### `src/wizard/tools/*.py`

| File | Description |
|------|-------------|
| `__init__.py` | Re-exports all public tool symbols |
| `formatting.py` | Shared notification utilities for MCP tool responses |
| `meeting_tools.py` | `get_meeting`, `ingest_meeting`, `save_meeting_summary` MCP tools |
| `mode_tools.py` | `get_modes`, `set_mode` MCP tools |
| `note_tools.py` | `rewind_task`, `what_am_i_missing` MCP tools |
| `query_tools.py` | Read-only query tools: `get_session`, `get_sessions`, `get_task`, `get_tasks` |
| `session_helpers.py` | Internal helpers for `session_tools.py` (context builder, prior-summaries, mid-session loop) |
| `session_tools.py` | `session_start`, `session_end`, `resume_session` MCP tools |
| `task_fields.py` | Task mutation and elicitation helpers shared across task tools |
| `task_tools.py` | `create_task`, `save_note`, `task_start`, `update_task` MCP tools |
| `triage_tools.py` | `what_should_i_work_on` MCP tool — scored work recommendation with LLM reasons |

### `src/wizard/repositories/*.py`

| File | Description |
|------|-------------|
| `__init__.py` | Re-exports all public repository symbols for backward compatibility |
| `analytics.py` | `AnalyticsRepository` — read-only queries for session/note/task statistics |
| `meeting.py` | `MeetingRepository` — CRUD for `Meeting` and `MeetingTasks` |
| `note.py` | `NoteRepository`, `build_rolling_summary` — CRUD and rolling summary logic for `Note` |
| `search.py` | `SearchRepository` — FTS5 full-text search across notes, sessions, meetings, tasks |
| `session.py` | `SessionRepository`, `find_latest_session_with_notes` — CRUD for `WizardSession` |
| `task.py` | `TaskRepository` — CRUD and query for `Task` with scoring and context |
| `task_state.py` | `TaskStateRepository` — derived signal updates for `TaskState` (note count, stale_days, etc.) |

### Other packages (not imported by the three-layer chain)

| Path | Description |
|------|-------------|
| `src/wizard/alembic/env.py` | Alembic migration environment; excludes FTS5 tables via `_include_object` |
| `src/wizard/alembic/versions/` | Migration scripts (raw DDL for FTS5, ORM-managed tables otherwise) |

## Hard Caps

| Scope | Cap | Enforcement |
|-------|-----|-------------|
| `src/wizard/**/*.py` | 500 lines | Pre-commit hook blocks commit |
| `tests/**/*.py` | 500 lines | Pre-commit hook blocks commit |
| Tools per file | 10 | Manual split trigger |

### Structural Split Triggers

| Trigger | Action |
|---------|--------|
| `integrations.py` adds a 3rd client | Split into `integrations/` package |
| `repositories.py` adds a 5th repo | Split into `repositories/` package |
| Any test file exceeds 500 lines | Split into `tests/test_<module>/` directory |

## Import Boundary Rules

Enforced by `scripts/pre-commit` — violations block commit:

| Layer file | Blocked imports |
|------------|----------------|
| `repositories/*.py` or `repositories.py` | `wizard.integrations`, `wizard.services`, `.integrations`, `.services` |
| `integrations/*.py` or `integrations.py` | `wizard.repositories`, `wizard.services`, `wizard.tools`, and their relative forms |
| `services/*.py` or `services.py` | `wizard.tools`, `.tools` |

**Pre-commit also runs:** line-count check, then import boundaries, then `ruff check`.

## Entry Points

| Command | Description |
|---------|-------------|
| `uv run server.py` | stdio MCP transport — dev use from repo |
| `wizard-server` | Installed MCP entry point (registered in pyproject.toml `[project.scripts]`) |
| `wizard` | CLI entry point (`wizard.cli.main:app`) |
| `uv run pytest` | Test runner — **never** `python -m pytest` (deps live in uv venv) |
| `uv run alembic upgrade head` | Run pending DB migrations (dev only) |
| `wizard update` | Upgrade install + run migrations + re-register agents (installed use) |

## Test Conventions

- **Scenario tests only** under `tests/scenarios/`
- No unit tests
- Test markers: `integration` (live API — excluded by default via `addopts = "-m 'not integration'"`)
- `asyncio_mode = "auto"` (pytest-asyncio)
- Ruff ignores `E402`, `E501`, `SIM117` in `tests/**`
