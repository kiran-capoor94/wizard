# Cognitive Tools — Design Spec

**Milestone:** 3 (sub-project C)  
**Version target:** v1.1.6  
**Branch:** `feat/c-cognitive-tools`  
**Dependencies:** Milestone 1 (TaskState + mental_model + session_state on main), Milestone 2 (async + ctx on main)  
**Spec reference:** WIZARD v1.1.6 Implementation Spec §8 (tools), §4 (schemas)

---

## Goal

Land three read-only cognitive tools (`rewind_task`, `what_am_i_missing`, `resume_session`), enrich existing response schemas with `TaskState`-sourced fields, and add the `session-resume` skill. No DB migrations. No external calls. No new dependencies.

---

## Scope

**In:**
- Three new tools: `rewind_task`, `what_am_i_missing`, `resume_session`
- Six new schemas: `TimelineEntry`, `RewindResponse`, `Signal`, `MissingResponse`, `ResumedTaskNotes`, `ResumeSessionResponse`
- Schema enrichments on existing types (see §2)
- `session-resume/SKILL.md` (new)
- `TaskContext.from_model(task, task_state)` classmethod to centralise enriched construction

**Out:**
- No DB migrations
- No changes to `config.py`, `services.py`, `prompts.py`, `resources.py`, `mcp_instance.py`, `integrations.py`
- No M4 items (Notion schema discovery, multi-agent, analytics)

---

## 1. Approach

Single PR. All three tools + schema enrichments + skill land together. Schema enrichments are driven by the tools' return types — they don't stand alone. The tools are all read-only with no external calls, so blast radius is contained to `schemas.py`, `tools.py`, `repositories.py`, and tests.

---

## 2. Schema enrichments

### 2.1 Existing schemas — additive changes

**`TaskContext`** — add four fields sourced from the `TaskState` row:

```python
notion_id: str | None          # from Task.notion_id
stale_days: int                # from TaskState.stale_days
note_count: int                # from TaskState.note_count
decision_count: int            # from TaskState.decision_count
```

All `TaskContext` construction sites currently build from `Task` fields only. Replace all inline constructions with a `TaskContext.from_model(task: Task, task_state: TaskState) -> TaskContext` classmethod. Construction sites: `session_start`, `task_start`, `get_meeting`, and the new `resume_session`.

**`NoteDetail`** — add one field:

```python
mental_model: str | None
```

`NoteDetail.from_model()` classmethod already exists — add the field there.

**`MeetingContext`** — one rename and two additions:

```python
already_summarised: bool       # was: has_summary
source_url: str | None         # new
source_type: str | None        # new
```

`has_summary` → `already_summarised` is a breaking rename. Update all construction sites and any skill/prompt references to `has_summary`.

**`TaskStartResponse`** — add one field:

```python
latest_mental_model: str | None
```

Populated in `task_start` by scanning `prior_notes` for the most recent note where `mental_model is not None`. Null if no note has a mental model.

**`SessionEndResponse`** — add one field:

```python
session_state_saved: bool
```

`session_end` already writes `SessionState` JSON to `WizardSession.session_state`. Wire the success/failure into the response.

**`SaveNoteResponse`** — field type change:

```python
# was: mental_model: str | None
mental_model_saved: bool       # true if mental_model was set
```

**`SaveMeetingSummaryResponse`** — field rename:

```python
# was: linked_task_ids: list[int]
tasks_linked: int              # count of successfully linked tasks
```

### 2.2 New schemas

**`TimelineEntry`**

```python
class TimelineEntry(BaseModel):
    note_id: int
    created_at: datetime.datetime
    note_type: NoteType
    preview: str               # content[:200]
    mental_model: str | None
```

**`RewindSummary`** (nested in `RewindResponse`)

```python
class RewindSummary(BaseModel):
    total_notes: int
    duration_days: int         # 0 if fewer than 2 notes
    last_activity: datetime.datetime  # most recent note's created_at, or Task.created_at
```

**`RewindResponse`**

```python
class RewindResponse(BaseModel):
    task: TaskContext
    timeline: list[TimelineEntry]  # sorted oldest first; empty list, never null
    summary: RewindSummary
```

**`Signal`**

```python
class Signal(BaseModel):
    type: str                  # rule identifier, e.g. "no_context", "stale"
    severity: Literal["high", "medium", "low"]
    message: str
```

**`MissingResponse`**

```python
class MissingResponse(BaseModel):
    signals: list[Signal]      # sorted: high → medium → low
```

**`ResumedTaskNotes`**

```python
class ResumedTaskNotes(BaseModel):
    task: TaskContext
    notes: list[NoteDetail]    # all notes for this task from resumed session, oldest first
    latest_mental_model: str | None
```

**`ResumeSessionResponse`**

```python
class ResumeSessionResponse(BaseModel):
    session_id: int                          # NEW session — use for all subsequent calls
    resumed_from_session_id: int
    session_state: SessionState | None       # null if prior session not cleanly closed
    working_set_tasks: list[TaskContext]     # live fetch; empty if session_state is null
    prior_notes: list[ResumedTaskNotes]      # grouped by task from resumed session
    unsummarised_meetings: list[MeetingContext]
    sync_results: list[SourceSyncStatus]
    daily_page: DailyPageResult | None
```

---

## 3. Tool implementations

All tools are `async def` with `ctx: Context` as first parameter. All log a `ToolCall` row at entry via `_log_tool_call`.

### 3.1 `rewind_task`

```python
async def rewind_task(ctx: Context, task_id: int) -> RewindResponse
```

**Logic:**
1. `db.get(Task, task_id)` — `ToolError` if not found
2. `task_state = db.get(TaskState, task_id)` — defensive `ToolError` if missing
3. `NoteRepository.get_for_task(db, task)` — returns all notes (dual-lookup included)
4. Sort notes by `created_at` ascending
5. Build `list[TimelineEntry]` from sorted notes (`content[:200]` for preview)
6. Compute `RewindSummary`:
   - `total_notes = len(notes)`
   - `duration_days = (notes[-1].created_at - notes[0].created_at).days` if `len(notes) >= 2` else `0`
   - `last_activity = notes[-1].created_at` if notes else `task.created_at`
7. Build `TaskContext.from_model(task, task_state)`
8. Return `RewindResponse`

No LLM. No external calls. No mutations.

### 3.2 `what_am_i_missing`

```python
async def what_am_i_missing(ctx: Context, task_id: int) -> MissingResponse
```

**Logic:**
1. `db.get(Task, task_id)` — `ToolError` if not found
2. `task_state = db.get(TaskState, task_id)` — `ToolError` if missing
3. Apply all seven rules. Collect matching `Signal` objects.
4. Rule 5 requires a count query: `SELECT COUNT(*) FROM note WHERE task_id=? AND note_type='investigation'`
5. Rule 7 requires an existence query: `SELECT 1 FROM note WHERE task_id=? AND mental_model IS NOT NULL LIMIT 1`
6. Sort signals: high first, then medium, then low
7. Return `MissingResponse(signals=signals)`

Both rule 5 and rule 7 queries are implemented inline in the tool using SQLModel `select` statements — not extracted to repo methods, as they are single-use.

**Seven rules** (all matching rules fire):

| # | Condition | type | severity | message |
|---|-----------|------|----------|---------|
| 1 | `task_state.note_count == 0` | `no_context` | high | `"No notes recorded for this task"` |
| 2 | `task_state.stale_days >= 3` | `stale` | medium | `f"No activity for {stale_days} days"` |
| 3 | `task_state.note_count > 0 and task_state.note_count <= 2` | `low_context` | medium | `"Very few notes — context may be shallow"` |
| 4 | `task_state.decision_count == 0 and task_state.note_count > 0` | `no_decisions` | medium | `"No decisions recorded"` |
| 5 | `investigation_count > 3 and task_state.decision_count == 0` | `analysis_loop` | high | `"Multiple investigations without a decision"` |
| 6 | `task_state.last_note_at is not None and task_state.stale_days >= 2` | `lost_context` | medium | `"Context may be degrading due to inactivity"` |
| 7 | `task_state.note_count >= 2 and not has_model` | `no_model` | medium | `"No mental model captured — understanding may be shallow"` |

Rules 2 and 6 both fire when `stale_days >= 3` — intentional. Rules 3 and 4 are guarded by `note_count > 0` to avoid redundancy with rule 1.

At most two additional DB queries (rules 5 and 7). No full content loaded. No LLM.

### 3.3 `resume_session`

```python
async def resume_session(ctx: Context, session_id: int | None = None) -> ResumeSessionResponse
```

**Logic:**
1. Find session to resume:
   - If `session_id` provided: `db.get(WizardSession, session_id)` — `ToolError` if not found
   - If not: `find_latest_session_with_notes(db)` — `ToolError` if none exists
2. Create new `WizardSession` row (this is the active session). `await ctx.set_state("current_session_id", new_session.id)`
3. `await ctx.report_progress(0, 3, "Syncing Jira...")` then `sync_service().sync_all()` with progress updates matching `session_start`
4. `ensure_daily_page()` via `notion_client()` — same as `session_start`
5. Deserialise `session_state`:
   - Non-null: `SessionState.model_validate_json(prior.session_state)` → fetch live `TaskContext.from_model(task, task_state)` for each `task_id` in `working_set`
   - Null: `await ctx.warning("Session was not cleanly closed — no structured state available. Falling back to note history.")` → `working_set_tasks = []`
6. Fetch `prior_notes` grouped by task: query all `Note` rows where `note.session_id == prior.id`, group by `task_id`, build `list[ResumedTaskNotes]`
7. `unsummarised_meetings` — same query as `session_start`
8. Return `ResumeSessionResponse`

`ctx.set_state` persists within the MCP session (single thread). Same contract as `session_start`.

---

## 4. Repository additions

### `find_latest_session_with_notes` (module-level in `repositories.py`)

```python
def find_latest_session_with_notes(db: Session) -> WizardSession | None:
    """Most recent WizardSession that has at least one associated Note."""
```

Query: select from `WizardSession` where an associated `Note` row exists (`note.session_id == wizardsession.id`), order by `created_at DESC`, limit 1.

### `TaskContext.from_model` classmethod (in `schemas.py`)

```python
@classmethod
def from_model(cls, task: Task, task_state: TaskState) -> "TaskContext":
    ...
```

Replaces all inline `TaskContext(...)` constructions in `tools.py`. All construction sites become `TaskContext.from_model(task, task_state)`.

---

## 5. Skill — `session-resume`

New file: `src/wizard/skills/session-resume/SKILL.md`

```markdown
---
name: session-resume
description: Resume a prior Wizard session in a new LLM thread. Use when the engineer says "continue where I left off", "pick up from yesterday", "what was I working on", or opens a new thread mid-task.
---

## Step 1 — Call the tool
Call `resume_session` from the wizard MCP server.
If the engineer mentions a specific session, pass that session_id.
Otherwise call with no arguments — Wizard will find the most recent session.

## Step 2 — Surface session_state first
If session_state is present, display it before anything else:

  "Resuming session [resumed_from_session_id]

   Intent:  [intent]
   Changed: [state_delta]
   Open:    [open_loops as bullet list]
   Next:    [next_actions as bullet list]
   Status:  [closure_status]"

If session_state is null, say:
  "Session [N] was not cleanly closed — no structured state available.
   Falling back to note history."
Then show the prior notes grouped by task.

## Step 3 — Show working set tasks
Display the working_set_tasks table: ID | Task | Status | Priority
These are the tasks the session was focused on, with current state from Jira/Notion.

## Step 4 — Ask
"Which task do you want to continue?"

## Important
- Use the NEW session_id for all subsequent calls — not resumed_from_session_id.
- Sync has already run. Task list is current.
- Only work within the current repository directory.
```

---

## 6. File map

| File | Change |
|---|---|
| `src/wizard/schemas.py` | Add 6 new schemas + `RewindSummary`; enrich `TaskContext`, `NoteDetail`, `MeetingContext`, `TaskStartResponse`, `SessionEndResponse`; rename `SaveNoteResponse.mental_model` → `mental_model_saved`; rename `SaveMeetingSummaryResponse.linked_task_ids` → `tasks_linked`; add `TaskContext.from_model` classmethod |
| `src/wizard/tools.py` | Add `rewind_task`, `what_am_i_missing`, `resume_session`; replace all inline `TaskContext(...)` constructions with `from_model`; wire `session_state_saved` into `session_end` response |
| `src/wizard/repositories.py` | Add `find_latest_session_with_notes` |
| `src/wizard/skills/session-resume/SKILL.md` | New file |
| `tests/test_tools.py` | Cover all 3 new tools; cover updated response fields on existing tools |
| `tests/test_repositories.py` | Cover `find_latest_session_with_notes` |
| `tests/test_schemas.py` or `tests/test_models.py` | Cover new schema classes and `TaskContext.from_model` |

---

## 7. Testing approach

Follow existing TDD pattern: red → green → refactor. One commit per logical task.

**`rewind_task`:** empty timeline (zero notes), single note, multiple notes (sort order, preview truncation at 200 chars, `duration_days` calculation), task not found raises `ToolError`.

**`what_am_i_missing`:** one test per rule that satisfies exactly that rule's condition. Confirm rules 2 and 6 both fire at `stale_days >= 3`. Confirm severity sort order. Confirm empty signals list when task is healthy (fresh task with recent notes, has mental model, has decision).

**`resume_session`:** explicit `session_id`, implicit (most recent), null `session_state` path (`ctx.warning` fires, `prior_notes` populated), non-null `session_state` path (`working_set_tasks` populated, `prior_notes` also populated). `ToolError` when no sessions with notes exist.

**`find_latest_session_with_notes`:** returns `None` when no sessions exist; returns `None` when sessions exist but none have notes; returns the most recent session that has notes (not the most recently created session without notes).

**Schema enrichment tests:** round-trip each new schema. `TaskContext.from_model` populates all four `TaskState` fields. `NoteDetail.from_model` populates `mental_model`. `MeetingContext.already_summarised` replaces `has_summary` correctly.

---

## 8. Conventions

- Follow existing import order: stdlib → third-party → `.local`
- `async def` with `ctx: Context` as first parameter
- `ToolError` for all user-visible errors (not raw exceptions)
- `await ctx.warning()` for non-fatal issues (`null session_state` in `resume_session`)
- `logger.info(...)` at tool entry with key parameter values
- Commit cadence: `feat:` for schema + tool work; `test:` for test-only commits; one commit per task
- Verify with `pytest -x tests/` before each commit
