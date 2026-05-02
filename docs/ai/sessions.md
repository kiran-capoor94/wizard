# sessions.md — AI fact sheet

## `session_start`

**Input**

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `agent_session_id` | `str \| None` | No | UUID from agent runtime; rejected if contains `..`, `/`, `\`, `:` |

**Output: `SessionStartResponse`**

| Field | Type | Notes |
|---|---|---|
| `session_id` | `int` | Newly created `WizardSession.id` |
| `continued_from_id` | `int \| None` | Set when `source == "compact"`; points to prior session |
| `open_tasks` | `list[TaskIndexEntry]` | Up to 20 non-blocked open tasks |
| `blocked_tasks` | `list[TaskIndexEntry]` | All blocked tasks |
| `unsummarised_meetings` | `list[MeetingContext]` | Meetings without a summary note |
| `wizard_context` | `dict \| None` | Knowledge store config (Notion or Obsidian details) |
| `skill_instructions` | `str \| None` | Always `None` in `session_start`; reserved field |
| `closed_sessions` | `list[ClosedSessionSummary]` | Sessions auto-closed during startup |
| `open_tasks_total` | `int` | Count of all open tasks (not just the first 20) |
| `source` | `str` | `"startup"` \| `"compact"` \| `"resume"` |
| `prior_summaries` | `list[PriorSessionSummary]` | 3 most recent closed sessions |
| `active_mode` | `str \| None` | Active skill mode for this session |
| `available_modes` | `list[ModeInfo]` | All configured modes |

**`source` field values**

| Value | Meaning |
|---|---|
| `"startup"` | Fresh session start (default) |
| `"compact"` | Agent compaction — session continues from prior |
| `"resume"` | Explicit resume via hook-written source file |

**Side effects**
- Writes `~/.wizard/sessions/<agent_session_id>/wizard_id` with integer session ID
- Calls `SessionCloser.close_recent_abandoned()` inline (no `ctx.sample()`)
- Dispatches `SessionCloser.close_abandoned_background()` as async task
- Calls `ts_repo.refresh_stale_days()` on all tasks
- Starts `mid_session_synthesis_loop` background task if `synthesis.enabled`

---

## `session_end`

**Input**

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `session_id` | `int` | Yes | From `session_start` |
| `summary` | `str` | Yes | PII-scrubbed before write |
| `intent` | `str` | Yes | PII-scrubbed before write |
| `working_set` | `list[int]` | Yes | Task IDs touched this session |
| `state_delta` | `str` | Yes | PII-scrubbed before write |
| `open_loops` | `list[str]` | Yes | Each item PII-scrubbed |
| `next_actions` | `list[str]` | Yes | Each item PII-scrubbed |
| `closure_status` | `"clean" \| "interrupted" \| "blocked"` | Yes | |
| `tool_registry` | `str \| None` | No | Opaque agent-supplied registry blob |

**Output: `SessionEndResponse`**

| Field | Type | Notes |
|---|---|---|
| `note_id` | `int` | ID of the `SESSION_SUMMARY` note written |
| `session_state_saved` | `bool` | `False` if serialisation failed |
| `closure_status` | `str \| None` | Echo of input |
| `open_loops_count` | `int` | `len(open_loops)` |
| `next_actions_count` | `int` | `len(next_actions)` |
| `intent` | `str \| None` | PII-scrubbed intent |
| `skill_instructions` | `str \| None` | Loaded from `SKILL_SESSION_END` |
| `skill_candidate` | `str \| None` | LLM-detected reusable pattern; set only if `working_set` non-empty |

**Side effects**
- Sets `WizardSession.closed_by = "user"`
- Writes `SessionState` JSON to `WizardSession.session_state`
- Saves a `NoteType.SESSION_SUMMARY` note
- Clears `current_session_id` from ctx state
- Cancels mid-session synthesis background task

---

## `resume_session`

**Input**

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `session_id` | `int \| None` | No | Explicit session to resume; if `None`, uses latest session with notes |
| `agent_session_id` | `str \| None` | No | UUID from agent runtime; rejected if contains path traversal chars |

**Output: `ResumeSessionResponse`**

| Field | Type | Notes |
|---|---|---|
| `session_id` | `int` | Newly created session ID |
| `resumed_from_session_id` | `int` | Source session ID |
| `continued_from_id` | `int \| None` | Same as `resumed_from_session_id` |
| `session_state` | `SessionState \| None` | Deserialised from prior session; `None` if session was not cleanly closed |
| `working_set_tasks` | `list[TaskContext]` | Task contexts for IDs in `session_state.working_set` |
| `prior_notes` | `list[ResumedTaskNotes]` | Up to 3 notes per task from prior session, most recent |
| `unsummarised_meetings` | `list[MeetingContext]` | Meetings without a summary note |
| `skill_instructions` | `str \| None` | Loaded from `SKILL_SESSION_RESUME` |
| `active_mode` | `str \| None` | Carried over from prior session |

**Side effects**
- Creates new `WizardSession` with `continued_from_id` pointing to prior session
- Writes `~/.wizard/sessions/<agent_session_id>/wizard_id` (mirrors `session_start`)

---

## `SessionState` schema

Stored as JSON in `WizardSession.session_state`. Written by `session_end`; read by `resume_session`.

| Field | Type | Notes |
|---|---|---|
| `intent` | `str` | Session intent; PII-scrubbed |
| `working_set` | `list[int]` | Task IDs touched this session |
| `state_delta` | `str` | Summary of changes; PII-scrubbed |
| `open_loops` | `list[str]` | Unresolved threads; each PII-scrubbed |
| `next_actions` | `list[str]` | Planned follow-ups; each PII-scrubbed |
| `closure_status` | `"clean" \| "interrupted" \| "blocked"` | |
| `tool_registry` | `str \| None` | Opaque agent-supplied blob |

---

## Continuity detection

### `find_previous_session_id()` — `tools/session_helpers.py`

Returns the most recently created `WizardSession.id` from the DB, or `None` if no sessions exist. Used by `session_start` when `source == "compact"` to link the new session to its predecessor via `continued_from_id`.

### `_is_safe_session_id()` — `tools/session_tools.py`

Rejects `agent_session_id` values that are empty or contain path traversal characters. Rejected characters: `/`, `\`, `:`. Also rejects strings containing `..`. Allows UUIDs and human-readable IDs like `session-2026-04-22-gemini-studio-free-tier`.

### `~/.wizard/sessions/<agent_session_id>/wizard_id`

- Written by **`session_start`** after DB flush — contains the integer `WizardSession.id`
- Written by **`resume_session`** after new session creation — same format
- **Not** written if `agent_session_id` is absent or unsafe

---

## `build_prior_summaries()`

Location: `tools/session_helpers.py`

- Calls `SessionRepository.get_prior_summaries(db, current_session_id)`
- Returns the **3 most recent closed sessions** as `list[PriorSessionSummary]`
- For each session: attempts to deserialise `session_state` JSON and extract `working_set` into `task_ids`
- Corrupt `session_state` is logged and `task_ids` defaults to `[]`

**`PriorSessionSummary` fields**

| Field | Type |
|---|---|
| `session_id` | `int` |
| `summary` | `str` |
| `closed_at` | `UTCDateTime` |
| `task_ids` | `list[int]` |
| `raw_session_state` | `str \| None` |

---

## `SessionCloser` — `services.py`

Finds and closes abandoned sessions (sessions with no `summary` and `closed_by` is `None` or `"hook"`).

**Two execution paths**

| Method | When | Threshold | Uses `ctx.sample()` |
|---|---|---|---|
| `close_recent_abandoned()` | Inline in `session_start` | Created within last **2h**, limit 3 | No — writes synthetic summary |
| `close_abandoned_background()` | Async task after `session_start` returns | Created **>2h** ago | No — writes synthetic summary |

**Closure logic (`_close_one`)**
1. Cancels any in-progress mid-session synthesis for the session
2. Fetches all notes for the session
3. Builds `SessionState` with `closure_status="interrupted"` and `working_set` from note `task_id` values
4. Writes synthetic summary: `"Auto-closed: N note(s) across M task(s). Last activity: <timestamp>."`
5. Sets `closed_by = "auto"` (if not already set)
6. Saves a `NoteType.SESSION_SUMMARY` note
7. Returns `ClosedSessionSummary`

**`ClosedSessionSummary` fields**

| Field | Type | Notes |
|---|---|---|
| `session_id` | `int` | |
| `summary` | `str` | PII-scrubbed synthetic summary |
| `closed_via` | `str` | Always `"synthetic"` from `SessionCloser` |
| `task_ids` | `list[int]` | Distinct task IDs from session notes |
| `note_count` | `int` | Total notes in session |

---

## `SessionStateMiddleware` — `middleware.py`

Runs **after** every tool call via `on_call_tool` (calls `call_next` first, then snapshots).

**Skipped tools**: `session_start`, `session_end` (defined in `_SKIP_TOOLS`)

**On every other tool call:**
1. Reads `current_session_id` from ctx state
2. Updates `WizardSession.last_active_at = datetime.datetime.now()`
3. Queries distinct `Note.task_id` values for the session (excludes `NULL` task_ids)
4. Builds partial `SessionState(closure_status="interrupted", working_set=[...], intent="", state_delta="", open_loops=[], next_actions=[])`
5. Writes JSON to `WizardSession.session_state`

**`snapshot_session_state(db, session_id)`** — public method, callable directly from tests (bypasses FastMCP middleware chain).
