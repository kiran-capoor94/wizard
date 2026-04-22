# Wizard — Developer Guide & Context

Wizard is a local memory layer for AI agents, providing persistent context across sessions, compounding knowledge over time, and on-demand work triage.

## Core Technologies
- **Language:** Python 3.13+
- **Agent Protocol:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) via [FastMCP](https://github.com/jlowin/fastmcp)
- **Database:** SQLite with [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic)
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Synthesis:** `OllamaAdapter` (native `/api/chat`) for Ollama backends; [LiteLLM](https://docs.litellm.ai/) for cloud providers (default model: `ollama/qwen3.5:4b`)
- **Package Manager:** [uv](https://docs.astral.sh/uv/)

## Building and Running

### Prerequisites
- Python 3.13+
- `uv` installed
- A local [Ollama](https://ollama.com/) server with `qwen3.5:4b` (optional but recommended for synthesis; cloud providers also supported)

### Install and Core Commands
```bash
# Install (one-time)
uv tool install git+https://github.com/kiran-capoor94/wizard.git

# Setup
wizard setup --agent [agent]                  # Initialize ~/.wizard/ and register agent

# MCP server
wizard-server                                 # Installed MCP server entry point (stdio)
uv run server.py                              # Run MCP server from repo (dev only)

# Migrations
wizard update                                 # Upgrade install, run migrations, re-register agents
uv run alembic upgrade head                   # Run migrations from repo (dev only)

# Development
uv sync                                       # Sync dependencies (dev)
uv run pytest                                 # Run full test suite
wizard doctor                                 # Run health checks
wizard analytics                              # View usage stats
wizard configure synthesis                    # List/manage LLM backends
wizard configure synthesis add                # Add a backend interactively
wizard configure synthesis test [N]           # Probe backend reachability
```

For development from repo, use `uv run` prefix. For installed packages, `wizard` and `wizard-server` are available directly.

## Project Layout

```text
server.py                    # Entry point — imports mcp_instance, tools, resources, prompts
src/wizard/
  cli/                       # Typer app subcommands
    main.py                  # setup, configure, doctor, analytics, update, uninstall
    serve.py                 # wizard-server entry point (installed MCP binary)
    capture.py               # wizard capture — synthesis trigger (called by hooks)
    configure.py             # configure knowledge-store + synthesis backends subcommands
    doctor.py                # 8-point health checks
    analytics.py             # Session/note/task analytics
  mcp_instance.py            # FastMCP app factory; registers ToolLoggingMiddleware + skills
  skills.py                  # Skill loader (reads ~/.wizard/skills/ at startup)
  tools/                     # MCP tools package (split by domain: session, task, triage, meeting, query)
  repositories/              # Query layer (package: task, note, meeting, session, task_state)
  resources.py               # 5 read-only MCP resources (wizard://* URIs)
  prompts.py                 # MCP prompt templates
  middleware.py              # ToolLoggingMiddleware — logs tool name on every invocation
  transcript.py              # TranscriptReader (JSONL parser for agent transcripts)
  synthesis.py               # Synthesiser (auto-capture — ordered backend failover)
  llm_adapters.py            # OllamaAdapter + LiteLLM completion wrapper, probe_backend_health, JSON parsing
  mid_session.py             # Background mid-session synthesis state
  toon.py                    # TOON encoder — compact tabular format for bulk task delivery
  models.py                  # SQLModel ORM: task, note, meeting, wizardsession, toolcall, task_state
  schemas.py                 # Pydantic response types for all MCP tools
  services.py                # SessionCloser — auto-closes abandoned sessions
  security.py                # SecurityService — regex PII scrubbing with allowlist
  config.py                  # Pydantic Settings + BackendConfig + JsonConfigSettingsSource
  database.py                # SQLite session factory (SQLModel engine) + run_migrations()
  deps.py                    # FastMCP Depends() provider functions
  exceptions.py              # ConfigurationError
  agent_registration.py      # Write MCP + hook config into agent files; refresh_hooks()
  alembic/                   # DB migrations — bundled in package for `wizard update`
  hooks/                     # Hook scripts — bundled in package, copied to ~/.wizard/hooks/ on setup
  skills/                    # FastMCP skills source (copied to ~/.wizard/skills/ by setup)
hooks/                       # Hook scripts source (also bundled as src/wizard/hooks/ for installs)
alembic/                     # DB migration scripts (dev use; bundled copy lives in src/wizard/alembic/)
tests/                       # pytest suite
```

## Database Schema

| Table | Purpose |
|-------|---------|
| `task` | Tasks synced from Jira/Notion + local creates |
| `note` | Notes (investigation/decision/docs/learnings/session_summary) |
| `meeting` | Meetings ingested from Krisp or Notion |
| `wizardsession` | Session records with serialised SessionState (Legacy name) |
| `toolcall` | Append-only telemetry (tool name + timestamp) (Legacy name) |
| `task_state` | Derived signals (1:1 with task): note counts, stale_days, last_touched |

**Invariant:** Scrub PII **before** writing to SQLite, not on read. Data at rest should never contain PII.

## Dependency Injection

`deps.py` provides plain provider functions wired into tools via FastMCP's `Depends()` system.
- `get_security()`, `get_task_repo()`, `get_meeting_repo()`, `get_note_repo()`, `get_task_state_repo()`.
- FastMCP resolves and caches providers per-request.
- In tests, call tool functions with deps as explicit kwargs.

## Architecture Highlights

### Session Continuity Tracking
Wizard tracks three layers: Agent session (UUID), Wizard session (Integer PK), and FastMCP session (Transport state).
- **Sub-agent suppression:** Hooks exit immediately if `agent_id` is present in the payload (top-level only).
- **Continuation detection:** `session_start` checks for `source == "compact"` to link to prior sessions.

### Auto-Capture (Transcript Synthesis)
- **SessionEnd hook** calls `wizard capture --close`.
- `Synthesiser` tries backends in priority order — first healthy local server wins, cloud providers always pass the health check. Backends are configured in `synthesis.backends` (ordered list of `BackendConfig` objects).
- Ollama backends use `OllamaAdapter` (native `/api/chat`, no grammar constraint, `think:false`); cloud backends route through LiteLLM.
- Raw transcript JSONL is persisted to `wizardsession.transcript_raw` at capture time, enabling re-synthesis after the agent deletes the file.
- Decoupled from MCP server; runs at hook time to avoid round-trip costs.
- Manage backends with `wizard configure synthesis` (list, add, remove, move, test).

### Session Personalization
- **SessionStart hook** fires with 80% probability gate.
- Refreshes `~/.claude/settings.json` with themed announcements, spinner verbs, and tips.
- Always auto-injects `wizard:session_start` tool call.

### Work Triage
- `what_should_i_work_on` scores tasks based on priority, recency, momentum, and simplicity.
- Modes: `focus`, `quick-wins`, `unblock`.
- LLM-sampled reasons are generated for top candidates.

## Coding Principles (Solo Engineer Mandates)

1. **SLAP (Single Layer of Abstraction):** Functions operate at one level. Tools orchestrate, they don't build SQL.
2. **Unidirectional dependencies:** `tools → services → integrations` and `tools → repositories`. Never sideways/backwards.
3. **No business logic in integrations:** Clients are thin wrappers for HTTP calls.
4. **DRY at the third occurrence:** Don't abstract after two uses.
5. **Idiomatic `_` prefix:** Only for genuinely private module/class names. No `_helpers.py`; use `helpers.py`.
6. **Classes over function bags:** Group stateful behavior into classes.
7. **No N+1 or N^2:** Batch-load with `.in_()` queries.
8. **One implementation, many interfaces:** CLI and MCP must call the same service methods.

## File Size & Structural Thresholds
- **Cap:** 500 lines per file (enforced by pre-commit).
- **Tools per file:** 10 (split trigger).
- **Split triggers:** `integrations.py` (3rd client), `repositories.py` (5th repo).

## PII Scrubbing Patterns
| Type | Replacement |
|------|-------------|
| Email | `[EMAIL_1]` |
| Phone | `[PHONE_1]` |
| Secrets | `[SECRET_1]` |
| Postcode | `[POSTCODE_1]` |
| NHS/NI | `[NHS_ID_1]`, `[NI_NUMBER_1]` |

Configure `scrubbing.allowlist` (e.g., `"ENG-\\d+"`) for identifiers that should pass through.
