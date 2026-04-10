# Codebase Simplification Design

**Date:** 2026-04-11
**Status:** Approved
**Goal:** Simplify implementation without losing robustness, features, or external contract

## Context

The wizard codebase (~2,130 LOC across 15 source files) has accumulated structural
residue from a series of refactors. The file/module structure is sound, but
implementation-level problems inflate the code and hurt debuggability:

- Async/sync mixing that blocks the event loop dishonestly
- 10 identical client-None guards across integration methods
- 5 of 9 MCP tools execute with zero logging
- 12 of 15 source files have no logger
- ~60 lines of duplicated try/except/log/return in WriteBackService
- Duplicated Note-to-NoteDetail conversions

## Approach: "Honest Sync"

Accept that the entire stack is synchronous (SQLite, httpx.Client, notion-client).
Simplify by making all tools sync, extracting repeated patterns, and adding
observability. No file structure changes. No new files.

## Changes

### 1. Async to Sync Conversion

**Files:** `tools.py`

Convert 4 async tool functions to sync:
- `session_start` — remove `async`, remove `ctx: Context = CurrentContext()` param,
  remove `await ctx.info()` and `await ctx.report_progress()` calls
- `session_end` — same
- `ingest_meeting` — same
- `create_task` — same

Remove imports: `from fastmcp import Context`, `from fastmcp.server.dependencies import CurrentContext`

All 9 tools become uniform `def fn(params) -> ResponseModel` shape.

**What we lose:** `ctx.info()` progress messages in 4 tools. These are cosmetic log
lines that Claude Code does not render as spinners or progress bars.

**What stays:** All tool names, parameters, return types. `ToolError` raises. MCP
registration via `mcp.tool()`.

### 2. Fail-Fast Client Init

**Files:** `integrations.py`

Add `_require_client()` method to both `JiraClient` and `NotionClient`:

```python
# JiraClient
def _require_client(self) -> httpx.Client:
    if self._client is None:
        raise ConfigurationError("Jira token not configured")
    return self._client

# NotionClient
def _require_client(self) -> NotionSdkClient:
    if self._client is None:
        raise ConfigurationError("Notion token not configured")
    return self._client
```

Replace all 10 inline `if self._client is None: raise ConfigurationError(...)` blocks
with `client = self._require_client()`. Each method then uses the narrowed `client`
local (type `Client`, not `Client | None`).

The optional-token construction pattern stays — sync service needs to handle partial
config gracefully.

### 3. NoteDetail.from_model() Classmethod

**Files:** `schemas.py`, `tools.py`, `resources.py`

Add classmethod to `NoteDetail`:

```python
@classmethod
def from_model(cls, note: "Note") -> "NoteDetail":
    assert note.id is not None
    return cls(
        id=note.id,
        note_type=note.note_type,
        content=note.content,
        created_at=note.created_at,
        source_id=note.source_id,
    )
```

Replace the 8-line conversion in `tools.py:78-89` (`task_start`) and the 8-line list
comprehension in `resources.py:57-67` (`task_context`) with:

```python
prior_notes = [NoteDetail.from_model(n) for n in notes]
```

### 4. WriteBackService._call() Helper

**Files:** `services.py`

Extract common try/except/log/return pattern into private helper:

```python
def _call(self, fn, error_label: str, **status_kwargs) -> WriteBackStatus:
    try:
        ok = fn()
        if ok:
            return WriteBackStatus(ok=True, **status_kwargs)
        return WriteBackStatus(ok=False, error=f"{error_label} failed")
    except Exception as e:
        logger.warning("%s failed: %s", error_label, e)
        return WriteBackStatus(ok=False, error=str(e))
```

4 simple methods (`push_task_status`, `push_task_status_to_notion`,
`push_meeting_summary`, `push_session_summary`) collapse to precondition check +
`self._call(...)`.

2 complex methods (`push_task_to_notion`, `push_meeting_to_notion`) use `_call`
internally for their API calls, reducing nesting from 4 levels to 2.

### 5. Logging and Observability

**Files:** `config.py`, `database.py`, `deps.py`, `security.py`, `repositories.py`,
`tools.py`, `resources.py`

Add `logger = logging.getLogger(__name__)` to every file that lacks it (12 of 15).

Targeted log additions:

| File | What | Level |
|------|------|-------|
| `config.py` | Config file path loaded (or missing) | `info` |
| `database.py` | Engine creation with db path | `info` |
| `deps.py` | Each singleton first-creation | `debug` |
| `security.py` | When PII is redacted: pattern count, not PII values | `info` |
| `repositories.py` | `get_by_id` failures before raising ValueError | `warning` |
| `tools.py` | Tool entry (name + key params), tool failure | `info` / `warning` |

No logging added to: `schemas.py`, `models.py`, `prompts.py`, `mcp_instance.py`,
`resources.py`.

### 6. Extract _extract_krisp_id Helper

**Files:** `integrations.py`, `services.py`

Move inline krisp_id URL parsing from `services.py:131-139` to a named helper in
`integrations.py` (next to existing `_extract_jira_key`):

```python
def _extract_krisp_id(url: str | None) -> str | None:
    if not url:
        return None
    try:
        segment = url.rstrip("/").split("/")[-1].split("?")[0].strip()
        return segment or None
    except Exception:
        logger.warning("Failed to extract krisp_id from URL: %s", url)
        return None
```

Replaces the silent `except Exception: pass` in `_sync_notion_meetings`.

## What Does NOT Change

- **File structure** — all 15 source files stay, no new files, no merges
- **schemas.py scope** — mixed model types stay in one file (222 lines, clear sections)
- **mappers.py classes** — namespace-as-class pattern stays, tests written against it
- **deps.py @lru_cache pattern** — consistent, tests use `.cache_clear()`
- **conftest.py module-reloading** — necessary given module-level singletons
- **Sync upsert logic** — `_sync_jira`, `_sync_notion_tasks`, `_sync_notion_meetings`
  stay as-is (dedup/transform logic differs enough that a generic template is forced)
- **`assert obj.id is not None`** — 11 occurrences stay as runtime invariant checks
- **MCP contract** — all tool names, parameters, return types, resource URIs, prompt
  functions unchanged

## Estimated Impact

- **Lines removed:** ~80-100 (boilerplate, async ceremony, duplicated guards)
- **Lines added:** ~30 (logging, helpers, from_model)
- **Net reduction:** ~50-70 lines
- **Files modified:** 10 (`tools.py`, `integrations.py`, `services.py`, `schemas.py`,
  `resources.py`, `config.py`, `database.py`, `deps.py`, `security.py`,
  `repositories.py`) — no structural changes
- **Test impact:** Tests for async tools need `async` removed. Integration tests need
  `_require_client` coverage. New logging assertions optional but recommended.

## Risk

Low. Every change is internal refactoring — the MCP contract (tool names, params,
return types, resource URIs, prompts) is unchanged. The biggest risk is the async
removal: if any MCP client depends on the tool being async, it would break. FastMCP
handles sync tools natively, so this risk is negligible.
