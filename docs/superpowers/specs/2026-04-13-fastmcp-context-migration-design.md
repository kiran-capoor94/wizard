# FastMCP Context Migration + session_end Six-Field Signature — Design

**Sub-project:** B + D (Milestone 2 of the v1.1.5 blueprint)
**Target release:** v1.1.5 (auto-bumped via `feat:` commits on merge)
**Date:** 2026-04-13
**Branch:** `feat/b-context-migration` off `main` at v1.1.4 (`65c8363`)
**Spec depends on:** Sub-project A shipped (TaskState, mental_model, session_state — all in v1.1.4)

## Purpose

Adopt FastMCP's `Context` injection across every tool to replace ad-hoc display patterns with first-class APIs (`ctx.info` / `ctx.warning` / `ctx.error` / `ctx.elicit` / `ctx.report_progress`). Bundle in the `session_end` signature change because it shares the same async/`Context` shift and consumes the `SessionState` Pydantic model already shipped in v1.1.4.

Why bundled: B (Context migration) and D (session_end six fields) are one coherent UX shift. Splitting them creates an awkward intermediate state where some tools are async with `ctx` and `session_end` is the lone sync hold-out, or vice versa.

## Scope

### 1. Async + `Context` injection across all 9 tools

Every tool in `src/wizard/tools.py` becomes:

```python
async def tool_name(ctx: Context, ...other params...) -> ResponseType:
```

The `Context` parameter is FIRST so positional callers (mostly tests) pass it explicitly. FastMCP injects `Context` automatically when the tool is invoked through MCP — tests construct a mock or test fixture.

**Tools to convert (all 9):**

`session_start`, `task_start`, `save_note`, `update_task_status`, `get_meeting`, `save_meeting_summary`, `session_end`, `ingest_meeting`, `create_task`.

The `with get_session() as db:` block stays synchronous — SQLite + SQLModel are sync, and that's fine inside an async function (no I/O wait).

**Per-tool conversion scope.** Every tool gets the async + `Context` shell. Beyond that, each tool gets only the additions called out below. The three tools with no extra body work (`save_meeting_summary`, `ingest_meeting`, `create_task`) are pure mechanical conversions.

| Tool                  | Shell | Progress (§5) | Elicit (§3/§4) | `set_state` (§7) | `get_state` (§7)              | Other body work          |
| --------------------- | ----- | ------------- | -------------- | ---------------- | ----------------------------- | ------------------------ |
| `session_start`       | ✓     | ✓             | —              | ✓                | —                             | three-step sync loop     |
| `task_start`          | ✓     | —             | —              | —                | ✓                             | stamp `session_id` on `_log_tool_call` |
| `save_note`           | ✓     | —             | ✓ mental_model | —                | ✓                             | stamp `session_id`; elicit branch |
| `update_task_status`  | ✓     | —             | ✓ outcome      | —                | ✓                             | elicit branch + Notion append |
| `get_meeting`         | ✓     | —             | —              | —                | ✓                             | stamp `session_id` |
| `save_meeting_summary`| ✓     | —             | —              | —                | — (`session_id` is a param)   | none                     |
| `session_end`         | ✓     | —             | —              | ✓ (delete)       | —                             | full rewrite (§6)        |
| `ingest_meeting`      | ✓     | —             | —              | —                | —                             | none                     |
| `create_task`         | ✓     | —             | —              | —                | —                             | none                     |

### 2. `ctx` API replacements

| Old pattern                                      | New pattern                                                                                                                               |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `logger.info("session_start")` at function entry | Keep — observability log, not user-facing. `ctx.info` is for client-visible messages.                                                     |
| Pre-existing `logger.warning` on caught errors   | Keep — server-side log.                                                                                                                   |
| `raise ToolError("Session not found")`           | Keep `ToolError` for fatal errors; add `await ctx.error(...)` BEFORE raising so the client sees the message in addition to the exception. |
| `_log_tool_call(db, "tool_name")`                | Keep unchanged — internal telemetry, not Context's job.                                                                                   |
| (new) sync progress reporting in `session_start` | `await ctx.report_progress(0, 3, "Syncing Jira...")` etc. around the three sync calls inside `SyncService.sync_all`.                      |
| (new) confirmation messages                      | `await ctx.info("Session 15 started.")` etc. at the end of tools where a confirmation aids the engineer.                                  |

### 3. `ctx.elicit` for `mental_model` in `save_note`

When `note_type ∈ {investigation, decision}` AND `mental_model` was not provided as a parameter, prompt the user inline:

```python
if note_type in (NoteType.INVESTIGATION, NoteType.DECISION) and mental_model is None:
    try:
        result = await ctx.elicit(
            "Optional: summarise what you now understand in 1-2 sentences (mental model). "
            "Press Enter to skip.",
            response_type=str,
        )
        if isinstance(result, AcceptedElicitation) and result.data:
            mental_model = result.data
        # DeclinedElicitation, CancelledElicitation, or empty data → leave None
    except Exception as e:
        # Client doesn't support elicitation, or the call failed.
        # Skip silently — mental_model is always optional.
        logger.debug("ctx.elicit unavailable for mental_model: %s", e)
```

The elicitation is **never blocking and never fatal**. Any failure (client doesn't support `elicit`, user declines, network error) results in `mental_model` staying `None`, the note being saved as-is, and the tool returning normally.

### 4. `ctx.elicit` for outcome summary in `update_task_status`

When `new_status == TaskStatus.DONE`, after the local update + TaskState bookkeeping but BEFORE the external write-backs, prompt for an outcome summary:

```python
if new_status == TaskStatus.DONE:
    try:
        result = await ctx.elicit(
            "Task closed. What was the outcome? (1-2 sentences, or press Enter to skip)",
            response_type=str,
        )
        if isinstance(result, AcceptedElicitation) and result.data:
            scrubbed = security().scrub(result.data).clean
            # Append to the Notion task page if we have a notion_id;
            # otherwise log and continue (Notion-less workflows are valid).
            if task.notion_id:
                writeback().append_task_outcome(task, scrubbed)
            else:
                logger.info("Task %d done with outcome but no notion_id; skipping notion append", task.id)
    except Exception as e:
        logger.debug("ctx.elicit unavailable for task outcome: %s", e)
```

**Two layers, mirroring the existing write-back pattern** (`services.py` already uses this split for every other Notion write):

- `NotionClient.append_paragraph_to_page(page_id: str, text: str) -> bool` — a single Notion paragraph block append against an existing page. Returns truthy on success, raises on transport failure. Lives in `src/wizard/integrations.py`.
- `WriteBackService.append_task_outcome(task: Task, summary: str) -> WriteBackStatus` — guards on `task.notion_id`, delegates via the existing `_call(fn, error_label)` helper so failures surface as a `WriteBackStatus(ok=False, error=...)` rather than raising. Lives in `src/wizard/services.py`.

The tool calls `WriteBackService.append_task_outcome`, never `NotionClient` directly. If Notion is not configured the result is a non-OK `WriteBackStatus` and the tool continues — never blocks.

The outcome summary is **not persisted as a Wizard Note** in this release. Persistence-as-note is deferred to M3 cognitive features (where `rewind_task` will surface it). The Notion write-back is the only side effect here.

### 5. `ctx.report_progress` during `session_start` sync

Inside `session_start`, before the `SyncService.sync_all()` call, plumb progress through the sync loop. `SyncService.sync_all()` returns a list of `SourceSyncStatus` results — we can call `report_progress` between each sync:

```python
await ctx.report_progress(0, 3, "Syncing Jira...")
jira_result = sync_service()._sync_jira(db)
await ctx.report_progress(1, 3, "Syncing Notion tasks...")
notion_tasks_result = sync_service()._sync_notion_tasks(db)
await ctx.report_progress(2, 3, "Syncing Notion meetings...")
notion_meetings_result = sync_service()._sync_notion_meetings(db)
await ctx.report_progress(3, 3, "Sync complete.")
sync_results = [jira_result, notion_tasks_result, notion_meetings_result]
```

This requires exposing `_sync_jira`, `_sync_notion_tasks`, `_sync_notion_meetings` on `SyncService` (currently private). Promote them to public methods (drop the leading underscore) since they are called from a different module.

`session_start` no longer calls `sync_service().sync_all()` — that becomes a thin wrapper for the CLI `wizard sync` command's use, retained to avoid breaking that surface.

### 6. `session_end` six-field signature

**Current signature:**

```python
def session_end(session_id: int, summary: str) -> SessionEndResponse
```

**New signature:**

```python
async def session_end(
    ctx: Context,
    session_id: int,
    summary: str,
    intent: str,
    working_set: list[int],
    state_delta: str,
    open_loops: list[str],
    next_actions: list[str],
    closure_status: Literal["clean", "interrupted", "blocked"],
) -> SessionEndResponse
```

**New behaviour:**

1. Construct a `SessionState` Pydantic model from the six new fields.
2. Serialise to JSON via `state.model_dump_json()`.
3. Store on `WizardSession.session_state` (column shipped in A).
4. Continue the existing summary scrub + Note creation + Notion daily page write-back.
5. After persistence, `await ctx.info("Session N closed. Status: <closure_status>.")`.
6. `await ctx.delete_state("current_session_id")` to clear the session-scoped state set by `session_start`. Keeps the lifecycle symmetric and prevents a stale ID from leaking into a subsequent `session_start` within the same long-lived MCP connection.

**Backwards compatibility:** none. The two-field signature is removed in this release. Callers (only the `session-end` skill prompt) must be updated to provide all eight params.

**Skill update:** `src/wizard/skills/session-end/SKILL.md` is rewritten to reflect the new collection flow. Skills are content, not code — single commit, no migration. (See §10.)

### 7. `ctx.set_state` / `ctx.get_state` for `session_id` propagation

Currently mid-session tools like `save_note` and `task_start` do not receive `session_id` — they operate on a task and the session linkage is implicit. With async + Context, we can plumb `session_id` cleanly through the request scope:

- `session_start` calls `await ctx.set_state("current_session_id", session.id)` after creating the session.
- Mid-session tools (`save_note`, `task_start`, `update_task_status`, `get_meeting`) read it via `await ctx.get_state("current_session_id")` if present, and use it to:
  - Stamp `Note.session_id` on saved notes (currently null for these tools).
  - Pass to `_log_tool_call` for ToolCall telemetry (currently null).

If `get_state` returns `None` (e.g. tool called outside a session_start), behaviour is unchanged from today: `session_id` is null on the resulting rows.

**Caveat per FastMCP docs:** `ctx.set_state` persists within the MCP session (single LLM thread), not across thread boundaries. `resume_session` (M3) handles cross-thread continuity by calling `ctx.set_state` itself when it lands.

### 8. Schema additions

In `src/wizard/schemas.py`:

- `SessionEndResponse` gains four optional echo fields so the response surfaces what was stored:
  - `closure_status: str | None = None`
  - `open_loops_count: int = 0`
  - `next_actions_count: int = 0`
  - `intent: str | None = None`
    These are observational — they let the engineer/automation confirm what landed in `session_state` without re-querying the DB.

- No other schema changes. Existing `SessionStartResponse`, `TaskStartResponse`, `SaveNoteResponse`, `UpdateTaskStatusResponse` etc. are unchanged — `Context` injection is invisible in the response.

### 9. Test infrastructure

Add `pytest-anyio>=0.0.0` (or `pytest-asyncio>=0.24.0` — pick one) to `[dependency-groups].dev` in `pyproject.toml`. Recommend **`pytest-asyncio`** with `asyncio_mode = "auto"` in `pyproject.toml`'s `[tool.pytest.ini_options]` block — every test in a file with `async def` becomes an async test automatically, no decorator needed.

Add a `MockContext` helper to `tests/helpers.py`:

```python
class MockContext:
    """Minimal Context double for async tool tests.
    Records calls; lets tests assert on them; configurable elicit response."""

    def __init__(self, elicit_response: str | None = None, supports_elicit: bool = True):
        self.info_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.error_calls: list[str] = []
        self.progress_calls: list[tuple[int, int, str | None]] = []
        self._state: dict[str, object] = {}
        self._elicit_response = elicit_response
        self._supports_elicit = supports_elicit

    async def info(self, msg: str) -> None: self.info_calls.append(msg)
    async def warning(self, msg: str) -> None: self.warning_calls.append(msg)
    async def error(self, msg: str) -> None: self.error_calls.append(msg)
    async def report_progress(self, current: int, total: int, message: str | None = None) -> None:
        self.progress_calls.append((current, total, message))
    async def set_state(self, key: str, value: object) -> None: self._state[key] = value
    async def get_state(self, key: str, default: object = None) -> object:
        return self._state.get(key, default)
    async def delete_state(self, key: str) -> None: self._state.pop(key, None)
    async def elicit(self, message: str, response_type=None):
        from fastmcp.client.elicitation import AcceptedElicitation, DeclinedElicitation
        if not self._supports_elicit:
            raise RuntimeError("Client does not support elicitation")
        if self._elicit_response is None:
            return DeclinedElicitation()
        return AcceptedElicitation(data=self._elicit_response)
```

**Existing tests are updated, not duplicated.** Every existing tool test in `tests/test_tools.py` becomes:

```python
async def test_xyz(db_session):
    from tests.helpers import MockContext
    ctx = MockContext()
    ...
    result = await tool_name(ctx, ...)
```

The `_patch_tools` helper continues to work — it patches module-level deps, not the tool signatures.

**New tests added:**

- `test_save_note_elicits_mental_model_for_investigation` — accept path stores model, decline path leaves null
- `test_save_note_does_not_elicit_for_docs_notes` — only investigation/decision trigger
- `test_save_note_handles_elicit_failure_gracefully` — `supports_elicit=False` → no error, mental_model stays null
- `test_update_task_status_elicits_outcome_when_done` — accept path triggers Notion append
- `test_update_task_status_does_not_elicit_for_in_progress` — only DONE triggers
- `test_session_start_reports_progress` — three progress calls observed
- `test_session_start_sets_current_session_id_in_ctx_state` — state observable post-call
- `test_save_note_uses_session_id_from_ctx_state_when_set` — Note.session_id stamped
- `test_save_note_session_id_null_when_no_ctx_state` — backwards-compatible default
- `test_session_end_persists_session_state` — JSON parses back to SessionState with all fields
- `test_session_end_emits_confirmation_via_ctx_info` — info call recorded
- `test_session_end_rejects_invalid_closure_status` — Pydantic validation surfaces
- `test_session_end_clears_current_session_id_from_ctx_state` — `delete_state` leaves the key absent post-call

### 10. Skill rewrite — `src/wizard/skills/session-end/SKILL.md`

The current skill instructs Claude Code to call `session_end(session_id, summary)`. Rewrite to:

1. Walk the engineer through collecting six fields (intent, working_set, state_delta, open_loops, next_actions, closure_status) per the v1.1.5 blueprint's `session_wrapup` prompt.
2. Call `session_end` with all eight parameters.
3. Surface the `SessionEndResponse` echo fields back to the engineer as confirmation.

Skill body content sourced verbatim from the v1.1.5 blueprint §14 `skills/session-end/SKILL.md`. No new prompt files in this release — `session_wrapup` as a separate FastMCP prompt is a future polish (M4) that's not strictly needed; the skill body carries the same instructions inline.

### 11. Out of scope (explicit non-goals)

| Out of scope here                                            | Lands in                                 |
| ------------------------------------------------------------ | ---------------------------------------- |
| `rewind_task`, `what_am_i_missing`, `resume_session` tools   | M3 (sub-project C)                       |
| Any other prompt or skill rewrites beyond `session-end`      | M4 (sub-project H)                       |
| Outcome summary persisted as a Wizard Note (vs. only Notion) | M3 (where `rewind_task` will surface it) |
| Notion schema discovery for `meeting_url`                    | M4 (sub-project E)                       |
| Multi-agent setup                                            | M4 (sub-project F)                       |
| `wizard analytics` CLI                                       | M4 (sub-project G)                       |

## Blast radius

**Files touched:**

- `src/wizard/tools.py` — every tool function (signature + body)
- `src/wizard/services.py` — promote three private sync methods to public; add `WriteBackService.append_task_outcome`
- `src/wizard/integrations.py` — add `NotionClient.append_paragraph_to_page` (one method)
- `src/wizard/schemas.py` — `SessionEndResponse` four optional fields
- `src/wizard/skills/session-end/SKILL.md` — rewrite
- `pyproject.toml` — add `pytest-asyncio` to dev deps; set `asyncio_mode = "auto"`
- `tests/helpers.py` — add `MockContext`
- `tests/test_tools.py` — update existing tests for async + ctx; add ~12 new tests
- `tests/test_services.py` — rename references to renamed methods (if any tests target them by old name)

**Files NOT touched:**

- `src/wizard/models.py`, `database.py`, `config.py`, `mappers.py`, `mcp_instance.py`, `mcp_config.py`, `repositories.py`, `deps.py`, `prompts.py`, `resources.py`, `security.py`
- All other skill files (Milestone 4 polish covers them)
- All CLI commands

**What breaks if wrong:**

- Async conversion: every test gets `await` and `async def`. Easy mass-edit, easy to verify (a single missing `await` shows up as a `coroutine was never awaited` warning).
- `session_end` signature change: existing callers must be updated. Only the skill calls it externally; internal CLI doesn't. Skill rewrite is covered.
- `ctx.elicit` failure handling: the try/except wrapper means client compatibility issues degrade gracefully rather than break tools.
- `pytest-asyncio` mode `auto`: silently converts every test in the suite. Existing sync tests stay sync (they have no `async def`). Mixed-mode is supported.

## Reviewer decisions

**Status:** All six recommendations accepted by reviewer on 2026-04-13. They are the binding decisions for the implementation plan.

| #   | Question                                                                                                                         | Decision (accepted)                                                                                                                                                                                     |
| --- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Test framework: `pytest-asyncio` or `pytest-anyio`?                                                                              | `pytest-asyncio` with `asyncio_mode = "auto"`. Better-known, simpler config, excellent docs. `anyio` is already transitively installed but the test plugin adds nothing here we don't have via asyncio. |
| 2   | `Context` parameter position: first or last?                                                                                     | **First.** Tests pass it positionally; first-position keeps test call-sites simple. FastMCP doesn't care about position when injecting.                                                                 |
| 3   | Outcome summary for `update_task_status(done)`: persist as Note too, or only Notion?                                             | **Notion only** in B+D. Note persistence couples to M3's `rewind_task` which will read it. Defer the dual-write to M3 to avoid building two retrieval paths.                                            |
| 4   | Should `_sync_jira`/`_sync_notion_tasks`/`_sync_notion_meetings` become public, or should `sync_all` accept a progress callback? | **Public methods.** Simpler, no callback indirection. Existing `sync_all` stays as a thin wrapper for the CLI.                                                                                          |
| 5   | `session_end` parameter ordering: `summary` first or buried among the six?                                                       | **`session_id, summary` first** (existing two), then the six new fields. Keeps the most-frequently-cited params at the front.                                                                           |
| 6   | `MockContext.elicit` decline behaviour: return `DeclinedElicitation` or empty data string?                                       | **`DeclinedElicitation`.** Mirrors the real protocol; tests can assert on type.                                                                                                                         |

## Release plan

- Branch: `feat/b-context-migration` from `main` at v1.1.4 (`65c8363`).
- TDD per global rules.
- Commits prefixed `feat:` for tool conversions (triggers minor → v1.1.5). Skill rewrite as `docs:`. Test-only commits as `test:`. Dep additions as `chore:`.
- PR title: `feat: FastMCP Context migration + session_end six-field signature`.
- Verification before PR: `pytest -x`, manual session walk-through (start → save_note → update_status → end) via Claude Code, `wizard doctor`.
- Code-reviewer agent before merge.

Estimated commit count: ~12-15 (similar to A, larger surface but mostly mechanical).
