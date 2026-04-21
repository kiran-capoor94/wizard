# Wizard — Developer Guide & Context

Wizard is a local memory layer for AI agents, providing persistent context across sessions, compounding knowledge over time, and on-demand work triage.

## Core Technologies
- **Language:** Python 3.14+
- **Agent Protocol:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) via [FastMCP](https://github.com/jlowin/fastmcp)
- **Database:** SQLite with [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic)
- **Migrations:** [Alembic](https://alembic.sqlalchemy.org/)
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Synthesis:** [Ollama](https://ollama.com/) (default model: `gemma4:latest-64k`)
- **Package Manager:** [uv](https://docs.astral.sh/uv/)

## Building and Running

### Prerequisites
- Python 3.14+
- `uv` installed
- `Ollama` with `gemma4:latest-64k` (optional but recommended for synthesis)

### Core Commands
```bash
uv sync                              # Sync dependencies
uv run wizard setup --agent [agent]  # Initialize ~/.wizard/ and register agent
uv run server.py                     # Run MCP server (stdio transport)
uv run alembic upgrade head          # Run pending DB migrations
uv run pytest                        # Run full test suite
uv run wizard doctor                 # Run health checks
uv run wizard analytics              # View usage stats
```

Always run via `uv run` to ensure the project's virtualenv dependencies are resolved correctly.

## Project Layout

```text
server.py                    # Entry point — imports mcp_instance, tools, resources, prompts
src/wizard/
  cli/                       # Typer app subcommands (setup, configure, doctor, analytics, etc.)
  mcp_instance.py            # FastMCP app factory; registers ToolLoggingMiddleware + skills
  skills.py                  # Skill loader (reads ~/.wizard/skills/ at startup)
  tools/                     # MCP tools package (split by domain: session, task, triage, meeting, query)
  resources.py               # 5 read-only MCP resources (wizard://* URIs)
  prompts.py                 # MCP prompt templates
  middleware.py              # ToolLoggingMiddleware — logs tool name on every invocation
  transcript.py              # TranscriptReader (JSONL parser for agent transcripts)
  synthesis.py               # Synthesiser (auto-capture via llama_server-compatible endpoint)
  models.py                  # SQLModel ORM: task, note, meeting, wizardsession, toolcall, task_state
  schemas.py                 # Pydantic response types for all MCP tools
  repositories.py            # Query layer over SQLite (TaskRepo, NoteRepo, etc.)
  services.py                # SessionCloser — auto-closes abandoned sessions
  security.py                # SecurityService — regex PII scrubbing with allowlist
  config.py                  # Pydantic Settings + JsonConfigSettingsSource
  database.py                # SQLite session factory (SQLModel engine)
  deps.py                    # FastMCP Depends() provider functions
  agent_registration.py      # Write MCP + hook config into agent files
  skills/                    # FastMCP skills source (copied to ~/.wizard/skills/ by setup)
hooks/                       # Agent hook scripts (SessionEnd, SessionStart)
alembic/                     # DB migration scripts
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
- `Synthesiser` reads agent transcripts (JSONL) and calls any LiteLLM-compatible provider via `LiteLLMAdapter`. Model is configured as a LiteLLM model string (e.g. `"ollama/gemma4:latest-64k"`).
- Decoupled from MCP server; runs at hook time to avoid round-trip costs.

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
