# Wizard — Developer Guide

## Coding Principles

Twelve rules that keep the codebase maintainable for a solo engineer:

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
12. **No mechanical LLM calls** — never use `ctx.sample()` for formatting,
    slug generation, or existence checks. LLM calls are for reasoning and
    content compression only.

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

## Full Reference

Detailed docs live in `docs/dev/` — loaded on demand, not at session start:

- Architecture & layout: [docs/dev/architecture.md](docs/dev/architecture.md)
- Configuration schema: [docs/dev/configuration.md](docs/dev/configuration.md)
- Database schema: [docs/dev/database.md](docs/dev/database.md)
- Dependency injection: [docs/dev/dependency-injection.md](docs/dev/dependency-injection.md)
- Doctor checks: [docs/dev/doctor-checks.md](docs/dev/doctor-checks.md)
- Agent registration: [docs/dev/agent-registration.md](docs/dev/agent-registration.md)
- Session continuity: [docs/dev/session-continuity.md](docs/dev/session-continuity.md)
- Auto-capture synthesis: [docs/dev/synthesis.md](docs/dev/synthesis.md)
- Session personalization: [docs/dev/session-personalization.md](docs/dev/session-personalization.md)
- MCP tools reference: [docs/dev/tools-reference.md](docs/dev/tools-reference.md)
- PII scrubbing: [docs/dev/pii-scrubbing.md](docs/dev/pii-scrubbing.md)
