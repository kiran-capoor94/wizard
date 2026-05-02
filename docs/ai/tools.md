# Wizard MCP Tools — AI Fact Sheet

Machine-optimised reference. One section per tool. No prose.

---

## `session_start` — `tools/session_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_session_id` | `str \| None` | `None` | Opaque agent-assigned session ID (e.g. UUID or slug). Used to key the sessions directory. Rejected if it contains `..`, `/`, `\\`, or `:`. |

### Outputs (`SessionStartResponse`)

| Field | Type | Description |
|---|---|---|
| `session_id` | `int` | New wizard session DB ID |
| `continued_from_id` | `int \| None` | Set if `source == "compact"` — ID of the session that was compacted |
| `source` | `str` | `"startup"` or `"compact"` (read from `sessions_dir/<agent_session_id>/source`) |
| `open_tasks` | `list[TaskIndexEntry]` | Up to 20 open tasks, ranked by state |
| `open_tasks_total` | `int` | Total count of open tasks (may exceed `len(open_tasks)`) |
| `blocked_tasks` | `list[TaskIndexEntry]` | All blocked tasks |
| `unsummarised_meetings` | `list[MeetingContext]` | Meetings with no summary yet |
| `wizard_context` | `dict \| None` | Arbitrary wizard config context |
| `skill_instructions` | `str \| None` | Always `None` on `session_start` (populated by `task_start`) |
| `closed_sessions` | `list[ClosedSessionSummary]` | Recently auto-closed abandoned sessions |
| `prior_summaries` | `list[PriorSessionSummary]` | Recently closed sessions surfaced as prior context |
| `active_mode` | `str \| None` | Mode applied to the new session (from config default or previous) |
| `available_modes` | `list[ModeInfo]` | All modes defined in `settings.modes.allowed` |

**`TaskIndexEntry` fields:** `id`, `name`, `status`, `priority`, `note_count`, `notes_by_type` (dict), `last_note_hint`, `last_worked_at`, `stale_days`

**`ClosedSessionSummary` fields:** `session_id`, `summary`, `closed_via` (`"sampling"` \| `"synthetic"` \| `"fallback"`), `task_ids`, `note_count`

**`PriorSessionSummary` fields:** `session_id`, `summary`, `closed_at`, `task_ids`, `raw_session_state`

**`MeetingContext` fields:** `id`, `title`, `category`, `created_at`, `already_summarised`, `source_url`, `source_type`

### Side Effects

- Inserts a `WizardSession` row.
- Sets `ctx` state key `current_session_id`.
- Writes `sessions_dir/<agent_session_id>/wizard_id` file.
- Calls `ts_repo.refresh_stale_days(db)` (updates `TaskState.stale_days`).
- Launches `session_closer.close_abandoned_background(session_id)` as a background `asyncio.Task`.
- If `agent_session_id` is set and `settings.synthesis.enabled`, launches the mid-session synthesis loop as a background `asyncio.Task`.
- Applies `settings.modes.default` to the new session if no mode is set.

### Errors

- `ToolError("Internal error: session was not assigned an id after flush")` — DB flush failure.

### Key Invariants

- **Must be called before `task_start`, `save_note`, or `session_end`.**
- `agent_session_id` values with `..`, `/`, `\\`, `:` are silently dropped (not rejected).

---

## `session_end` — `tools/session_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `session_id` | `int` | required | Session ID from `session_start` |
| `summary` | `str` | required | Human-readable session summary (PII scrubbed) |
| `intent` | `str` | required | One-line goal of the session (PII scrubbed) |
| `working_set` | `list[int]` | required | Task IDs worked on this session |
| `state_delta` | `str` | required | What changed vs session start (PII scrubbed) |
| `open_loops` | `list[str]` | required | Unresolved threads to carry forward (each PII scrubbed) |
| `next_actions` | `list[str]` | required | Concrete next steps (each PII scrubbed) |
| `closure_status` | `Literal["clean","interrupted","blocked"]` | required | How the session ended |
| `tool_registry` | `str \| None` | `None` | Serialised registry of tools used this session |

### Outputs (`SessionEndResponse`)

| Field | Type | Description |
|---|---|---|
| `note_id` | `int` | ID of the `session_summary` note written |
| `session_state_saved` | `bool` | Whether `WizardSession.session_state` was serialised successfully |
| `closure_status` | `str \| None` | Echo of input `closure_status` |
| `open_loops_count` | `int` | Count of `open_loops` |
| `next_actions_count` | `int` | Count of `next_actions` |
| `intent` | `str \| None` | PII-scrubbed intent string |
| `skill_instructions` | `str \| None` | Content of `SKILL_SESSION_END` post-action skill |
| `skill_candidate` | `str \| None` | LLM-sampled description of a reusable pattern, or `None` |

### Side Effects

- Updates `WizardSession` row: sets `session_state` (JSON), `summary`, `closed_by = "user"`.
- Inserts a `Note` row with `note_type = "session_summary"`.
- Cancels the mid-session synthesis background task for this `agent_session_id` (if any).
- Deletes `ctx` state key `current_session_id`.
- If `working_set` is non-empty, samples LLM to detect a `skill_candidate`.

### Errors

- `ToolError(f"Session {session_id} not found")` — session ID does not exist.
- `ToolError("Internal error: session was not assigned an id after flush")` — DB flush failure.
- `ToolError` wrapping `ValueError` from session state serialisation.

### Key Invariants

- **Call `session_start` first to obtain `session_id`.**
- PII is scrubbed from `summary`, `intent`, `state_delta`, each `open_loops` item, and each `next_actions` item before writing.

---

## `resume_session` — `tools/session_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `session_id` | `int \| None` | `None` | Prior session to resume. If `None`, finds the latest session that has notes. |
| `agent_session_id` | `str \| None` | `None` | Opaque agent ID. Same safety rules as `session_start`. |

### Outputs (`ResumeSessionResponse`)

| Field | Type | Description |
|---|---|---|
| `session_id` | `int` | Newly created session ID |
| `resumed_from_session_id` | `int` | Prior session ID that was resumed |
| `continued_from_id` | `int \| None` | Same as `resumed_from_session_id` |
| `session_state` | `SessionState \| None` | Deserialised `SessionState` from the prior session, or `None` if unavailable |
| `working_set_tasks` | `list[TaskContext]` | Task contexts for IDs listed in prior `session_state.working_set` |
| `prior_notes` | `list[ResumedTaskNotes]` | Notes grouped by task (up to 3 per task, most recent) |
| `unsummarised_meetings` | `list[MeetingContext]` | Same as `session_start` |
| `skill_instructions` | `str \| None` | Content of `SKILL_SESSION_RESUME` post-action skill |
| `active_mode` | `str \| None` | Mode copied from the prior session |

**`SessionState` fields:** `intent`, `working_set` (list[int]), `state_delta`, `open_loops`, `next_actions`, `closure_status`, `tool_registry`

**`ResumedTaskNotes` fields:** `task` (TaskContext), `notes` (list[NoteDetail], max 3), `latest_mental_model`

### Side Effects

- Inserts a new `WizardSession` row with `continued_from_id` set to the prior session.
- Sets `ctx` state key `current_session_id` to the new session ID.
- Writes `sessions_dir/<agent_session_id>/wizard_id` file (if `agent_session_id` provided).

### Errors

- `ToolError(f"Session {session_id} not found")` — explicit session ID not found.
- `ToolError("No sessions with notes found")` — no prior sessions when `session_id` is `None`.
- `ToolError` on DB ID assignment failures.

---

## `task_start` — `tools/task_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | `int` | required | Task ID (from `session_start` open/blocked task index) |

### Outputs (`TaskStartResponse`)

| Field | Type | Description |
|---|---|---|
| `task` | `TaskContext` | Full task context |
| `compounding` | `bool` | `True` if prior notes exist |
| `notes_by_type` | `dict[str, int]` | Note counts keyed by type name (e.g. `{"investigation": 3, "decision": 1}`) |
| `prior_notes` | `list[NoteDetail]` | Up to 5 key notes (priority: failure → decision → mental_model → recent) |
| `total_notes` | `int` | Total note count including notes not returned |
| `older_notes_available` | `bool` | `True` if `total_notes > len(prior_notes)`; use `rewind_task` for full history |
| `rolling_summary` | `str \| None` | Synthesised from mental models of all notes (from `TaskState`) |
| `latest_mental_model` | `str \| None` | Most recent mental model string across all notes |
| `skill_instructions` | `str \| None` | Content of `SKILL_TASK_START`; sent only on the **first** `task_start` call per session (deduplicated via ctx state) |

**`TaskContext` fields:** `id`, `name`, `status`, `priority`, `category`, `due_date`, `source_id`, `source_url`, `last_note_type`, `last_note_preview` (first 300 chars), `last_worked_at`, `stale_days`, `note_count`, `decision_count`

**`NoteDetail` fields:** `id`, `note_type`, `content`, `created_at`, `mental_model`

### Side Effects

- Read-only DB access (no writes).
- Sets `ctx` state key `task_start_skill_delivered = True` after first call.

### Errors

- `ToolError` wrapping `ValueError` if `task_id` not found.

### Key Invariants

- **`session_start` must be called first** (to obtain valid `task_id`s).
- Note selection tier order: (0) all failure notes, (1) all decision notes, (2) notes with mental_models, (3) most recent — capped at 5 total.
- `skill_instructions` is sent only once per session to avoid context bloat.

---

## `create_task` — `tools/task_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Task name (PII scrubbed) |
| `priority` | `TaskPriority` | `"medium"` | `"low"` \| `"medium"` \| `"high"` |
| `category` | `TaskCategory` | `"issue"` | `"issue"` \| `"bug"` \| `"investigation"` |
| `source_id` | `str \| None` | `None` | External system ID (e.g. Jira issue key). Triggers upsert. |
| `source_type` | `str \| None` | `None` | Source system label (e.g. `"jira"`, `"notion"`) |
| `source_url` | `str \| None` | `None` | Deep link to the source |
| `status` | `TaskStatus` | `"todo"` | `"todo"` \| `"in_progress"` \| `"blocked"` \| `"done"` \| `"archived"` |
| `meeting_id` | `int \| None` | `None` | If set, links the new task to this meeting |

Status aliases accepted: `completed` → `done`, `complete` → `done`, `finish` → `done`, `finished` → `done`, `open` → `todo`, `pending` → `todo`, `wip` → `in_progress`, `doing` → `in_progress`, `inactive` → `archived`.

### Outputs (`CreateTaskResponse`)

| Field | Type | Description |
|---|---|---|
| `task_id` | `int` | ID of the created or existing task |
| `already_existed` | `bool` | `True` if returned an existing task (source_id upsert or name duplicate) |

### Side Effects

- Inserts a `Task` row and a corresponding `TaskState` row.
- Links the task to `meeting_id` via `MeetingTasks` join row (if `meeting_id` provided).
- If `source_id` is set, performs upsert by `source_id` — no duplicate-name check.
- If no `source_id`, elicits user confirmation before returning an existing task with a matching name.

### Errors

- `ToolError("Internal error: task was not assigned an id after flush")` — DB flush failure.

---

## `update_task` — `tools/task_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | `int` | required | Task to update |
| `status` | `TaskStatus \| None` | `None` | New status (same aliases as `create_task`) |
| `priority` | `TaskPriority \| None` | `None` | New priority |
| `due_date` | `str \| None` | `None` | ISO-8601 date string |
| `name` | `str \| None` | `None` | New task name (PII scrubbed) |
| `source_url` | `str \| None` | `None` | New source URL |

### Outputs (`UpdateTaskResponse`)

| Field | Type | Description |
|---|---|---|
| `task_id` | `int` | The updated task ID |
| `updated_fields` | `list[str]` | Names of fields that were changed |
| `task_state_updated` | `bool` | `True` if `TaskState` was also updated (happens when `status` changed) |

### Side Effects

- Updates the `Task` row for the fields provided.
- If `status` changed, calls `t_state_repo.on_status_changed(db, task_id)`.
- If `status == "done"`, elicits user confirmation before proceeding. Returns empty `updated_fields` if user declines.

### Errors

- `ToolError("At least one field must be provided to update_task")` — all params are `None`.
- `ToolError` wrapping `ValueError` if `task_id` not found.
- `ToolError("Internal error: task was not assigned an id after flush")` — DB flush failure.

### Key Invariants

- **`update_task_status` is deprecated — always use `update_task`.**
- Only non-`None` fields are written; passing `None` leaves the field unchanged.

---

## `get_task` — `tools/query_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | `int` | required | Task to retrieve |

### Outputs (`TaskDetailResponse`)

| Field | Type | Description |
|---|---|---|
| `task` | `TaskSummary` | Task fields including `stale_days`, `note_count`, `last_worked_at` |
| `notes` | `list[NoteDetail]` | All notes, ascending by `created_at` |
| `latest_mental_model` | `str \| None` | Most recent mental model from notes |

**`TaskSummary` fields:** `id`, `name`, `status`, `priority`, `category`, `source_id`, `source_type`, `source_url`, `stale_days`, `note_count`, `due_date`, `last_worked_at`

### Side Effects

None. Read-only.

### Errors

- `ToolError(f"Task {task_id} not found")` — task does not exist.

---

## `get_tasks` — `tools/query_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | `list[str] \| None` | `None` | Filter by status values (e.g. `["todo","in_progress"]`) |
| `source_type` | `str \| None` | `None` | Filter by source system (e.g. `"jira"`) |
| `limit` | `int` | `50` | Max items per page |
| `cursor` | `str \| None` | `None` | Opaque pagination cursor from a prior response |

### Outputs (`GetTasksResponse`)

| Field | Type | Description |
|---|---|---|
| `items` | `list[TaskSummary]` | Page of task summaries |
| `next_cursor` | `str \| None` | Cursor for the next page; `None` if last page |
| `total_returned` | `int` | Count of items in this response |

### Side Effects

None. Read-only.

### Errors

- `ToolError("Invalid cursor")` — malformed cursor string.

---

## `save_note` — `tools/task_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | `int` | required | Task this note belongs to |
| `note_type` | `NoteType` | required | `"investigation"` \| `"decision"` \| `"docs"` \| `"learnings"` \| `"session_summary"` \| `"failure"` |
| `content` | `str` | required | Note body. PII scrubbed. Compressed to ≤1000 chars if longer. Hard cap: 100,000 chars. |
| `mental_model` | `str \| None` | `None` | 2-3 sentence understanding snapshot. PII scrubbed. Compressed if >1000 chars. |

### Outputs (`SaveNoteResponse`)

| Field | Type | Description |
|---|---|---|
| `note_id` | `int` | ID of the saved (or existing duplicate) note |
| `mental_model_saved` | `bool` | `True` if `mental_model` is stored on the note |
| `was_duplicate` | `bool` | `True` if content hash matched an existing note (skipped re-insert) |

### Side Effects

- Inserts a `Note` row (or updates `mental_model` on existing if duplicate).
- Calls `t_state_repo.on_note_saved(db, task_id, note_type, created_at)` — updates `TaskState.note_count`, `decision_count`, `last_note_at`.
- PII scrubbed from `content` and `mental_model` before write.
- Content >1000 chars is LLM-compressed (preserving file paths, function names, error messages).

### Errors

- `ToolError("Content exceeds 100k character limit")` — content too large.
- `ToolError("Internal error: note was not assigned an id after flush")` — DB flush failure.
- `ToolError` wrapping `ValueError` if `task_id` not found.

### Key Invariants

- **`session_start` must be called first** (note is linked to `current_session_id` from ctx state).
- Deduplication is hash-based (`SHA-256` of PII-scrubbed content). Duplicate returns the original note ID with `was_duplicate: true`.
- **Use `mental_model` after 2+ notes on a task** to capture a snapshot of current understanding.

---

## `get_meeting` — `tools/meeting_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `meeting_id` | `int` | required | Meeting ID from `unsummarised_meetings` in `session_start` |

### Outputs (`GetMeetingResponse`)

| Field | Type | Description |
|---|---|---|
| `meeting_id` | `int` | Meeting ID |
| `title` | `str` | Meeting title |
| `category` | `MeetingCategory` | `"standup"` \| `"planning"` \| `"retro"` \| `"one_on_one"` \| `"general"` |
| `content` | `str` | Full meeting transcript / body |
| `already_summarised` | `bool` | `True` if a summary already exists |
| `existing_summary` | `str \| None` | Prior summary if one exists |
| `open_tasks` | `list[TaskContext]` | Tasks linked to this meeting with status `todo`, `in_progress`, or `blocked` |
| `skill_instructions` | `str \| None` | Content of `SKILL_MEETING` post-action skill |

### Side Effects

None. Read-only.

### Errors

- `ToolError` wrapping `ValueError` if `meeting_id` not found.

### Key Invariants

- **Get meeting IDs from `session_start.unsummarised_meetings`**, not by guessing.

---

## `ingest_meeting` — `tools/meeting_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `title` | `str` | required | Meeting title (PII scrubbed) |
| `content` | `str` | required | Transcript or notes (PII scrubbed) |
| `source_id` | `str \| None` | `None` | Dedup key from external system (e.g. Krisp meeting ID) |
| `source_type` | `str \| None` | `None` | Source label (e.g. `"krisp"`) |
| `source_url` | `str \| None` | `None` | Deep link to meeting in source system |
| `category` | `MeetingCategory` | `"general"` | Meeting category |

### Outputs (`IngestMeetingResponse`)

| Field | Type | Description |
|---|---|---|
| `meeting_id` | `int` | ID of the meeting row (new or existing) |
| `already_existed` | `bool` | `True` if `source_id` matched an existing meeting |

### Side Effects

- Inserts a `Meeting` row (if `source_id` is absent or unmatched).
- PII scrubbed from `title` and `content` before write.
- No insert if `source_id` already exists (`already_existed: true`).

### Errors

- `ToolError("Internal error: meeting was not assigned an id after flush")` — DB flush failure.

---

## `save_meeting_summary` — `tools/meeting_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `meeting_id` | `int` | required | Meeting to summarise |
| `summary` | `str` | required | LLM-generated summary (PII scrubbed) |
| `task_ids` | `list[int] \| None` | `None` | Task IDs to link to this meeting |

### Outputs (`SaveMeetingSummaryResponse`)

| Field | Type | Description |
|---|---|---|
| `note_id` | `int` | ID of the `docs` note written for this summary |
| `tasks_linked` | `int` | Total count of tasks linked to the meeting (including previously linked) |

### Side Effects

- Updates `Meeting.summary` field.
- Inserts a `Note` row with `note_type = "docs"` linked to the meeting.
- Inserts `MeetingTasks` rows for each confirmed `task_id`.
- Elicits user confirmation before linking tasks (if `task_ids` provided). Skips link if not confirmed.
- PII scrubbed from `summary` before write.

### Errors

- `ToolError` wrapping `ValueError` if `meeting_id` not found.
- `ToolError("Internal error: meeting/note was not assigned an id after flush")` — DB flush failure.

### Key Invariants

- **`session_start` must be called first** (note is linked to `current_session_id`).

---

## `search` — `tools/query_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str` | required | Search terms. Must be non-empty after strip. |
| `limit` | `int` | `10` | Max results |
| `entity_type` | `Literal["note","session","meeting","task"] \| None` | `None` | Filter to one entity type. `None` = all types. |

### Outputs (`SearchResponse`)

| Field | Type | Description |
|---|---|---|
| `results` | `list[SearchResult]` | Ranked results |
| `total` | `int` | Count of results returned |

**`SearchResult` fields:** `entity_type`, `entity_id`, `title`, `snippet`, `created_at`, `task_id` (set for notes; `None` for other types)

### Side Effects

None. Read-only. Uses SQLite FTS5 with BM25 ranking.

### Errors

- `ToolError("query must not be empty")` — blank query.

---

## `what_should_i_work_on` — `tools/triage_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `session_id` | `int` | required | Active session ID (schema contract; value is unused internally) |
| `mode` | `Literal["focus","quick-wins","unblock"]` | `"focus"` | Scoring mode |
| `time_budget` | `str \| None` | `None` | Available time: `"30m"`, `"2h"`, `"half-day"`, `"full-day"` |

Mode scoring weights:

| Mode | priority | recency | momentum | simplicity |
|---|---|---|---|---|
| `focus` | 0.50 | 0.30 | 0.20 | 0.00 |
| `quick-wins` | 0.20 | 0.15 | 0.15 | 0.50 |
| `unblock` | 0.40 | 0.40 | 0.20 | 0.00 |

### Outputs (`WorkRecommendationResponse`)

| Field | Type | Description |
|---|---|---|
| `recommended_task` | `TaskRecommendation \| None` | Top-ranked task, or `None` if no workable tasks |
| `alternatives` | `list[TaskRecommendation]` | Next 3 candidates |
| `skipped_blocked` | `int` | Count of blocked tasks excluded (non-`unblock` mode) |
| `message` | `str \| None` | Set when no tasks available |

**`TaskRecommendation` fields:** `task_id`, `name`, `priority`, `status`, `score` (float), `reason` (LLM-sampled, ≤25 words), `momentum` (`"new"` \| `"active"` \| `"cooling"` \| `"cold"`), `last_note_preview`

### Side Effects

- Samples LLM for reason text on up to 4 tasks. Falls back to deterministic reason on LLM error.
- Emits `SKILL_TRIAGE` content as a ctx info message.

### Errors

None raised. Returns empty response with `message` if no tasks.

### Key Invariants

- **`session_id` is required by contract** but is not validated against the DB. Pass the ID from `session_start`.
- `unblock` mode only surfaces tasks with `status == "blocked"`.
- `time_budget == "30m"` boosts `in_progress` tasks (+0.1) and penalises zero-note tasks (−0.1).

---

## `get_modes` — `tools/mode_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `session_id` | `int \| None` | `None` | If provided, returns the active mode for this session |

### Outputs (`GetModesResponse`)

| Field | Type | Description |
|---|---|---|
| `available_modes` | `list[ModeInfo]` | All modes from `settings.modes.allowed` with descriptions |
| `active_mode` | `str \| None` | Active mode for the session, or `None` |

**`ModeInfo` fields:** `name`, `description` (from SKILL.md YAML frontmatter)

### Side Effects

None. Read-only.

### Errors

None raised.

---

## `set_mode` — `tools/mode_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `session_id` | `int` | required | Session to update |
| `mode_name` | `str \| None` | required | Mode skill name to activate, or `None` to clear |

### Outputs (`SetModeResponse`)

| Field | Type | Description |
|---|---|---|
| `active_mode` | `str \| None` | The now-active mode, or `None` if cleared |
| `description` | `str \| None` | Skill description from SKILL.md frontmatter |
| `instruction` | `str \| None` | `"Invoke skill: <mode_name> now to load this mode's behavior."` or `None` if cleared |

### Side Effects

- Updates `WizardSession.active_mode` for the given session.

### Errors

- `ToolError(f"'{mode_name}' is not in allowed modes: ...")` — mode not in `settings.modes.allowed`.
- `ToolError` wrapping `ValueError` if `session_id` not found.

---

## `get_session` — `tools/query_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `session_id` | `int` | required | Session to retrieve |

### Outputs (`SessionDetailResponse`)

| Field | Type | Description |
|---|---|---|
| `session` | `SessionSummary` | Session metadata |
| `session_state` | `SessionState \| None` | Deserialised `SessionState` JSON, or `None` if not set or parse error |
| `notes` | `list[NoteDetail]` | All notes for this session |

**`SessionSummary` fields:** `id`, `created_at`, `updated_at`, `closure_status` (raw `closed_by` value), `intent` (from `session_state`), `note_count`

### Side Effects

None. Read-only.

### Errors

- `ToolError(f"Session {session_id} not found")` — session does not exist.

---

## `get_sessions` — `tools/query_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `closure_status` | `str \| None` | `None` | Filter by `closed_by` value (e.g. `"user"`) |
| `limit` | `int` | `20` | Max items per page |
| `cursor` | `str \| None` | `None` | Opaque pagination cursor |

### Outputs (`GetSessionsResponse`)

| Field | Type | Description |
|---|---|---|
| `items` | `list[SessionSummary]` | Page of session summaries, newest first |
| `next_cursor` | `str \| None` | Cursor for next page; `None` if last page |
| `total_returned` | `int` | Count of items in this response |

### Side Effects

None. Read-only.

### Errors

- `ToolError("Invalid cursor")` — malformed cursor.

---

## `rewind_task` — `tools/note_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | `int` | required | Task to reconstruct history for |

### Outputs (`RewindResponse`)

| Field | Type | Description |
|---|---|---|
| `task` | `TaskContext` | Current task context |
| `timeline` | `list[TimelineEntry]` | All notes, sorted oldest first. Never `null`; empty list if no notes. |
| `summary` | `RewindSummary` | Aggregate statistics |

**`TimelineEntry` fields:** `note_id`, `created_at`, `note_type`, `preview` (first 200 chars of content), `mental_model`

**`RewindSummary` fields:** `total_notes`, `duration_days` (0 if fewer than 2 notes), `last_activity` (UTC datetime)

### Side Effects

None. Read-only.

### Errors

- `ToolError` wrapping `ValueError` if `task_id` not found.
- `ToolError(f"TaskState missing for task {task_id}")` — `TaskState` row absent.

### Key Invariants

- Use `rewind_task` when `task_start.older_notes_available == true` to get the full history.

---

## `what_am_i_missing` — `tools/note_tools.py`

### Inputs

| Parameter | Type | Default | Description |
|---|---|---|---|
| `task_id` | `int` | required | Task to diagnose |

### Outputs (`MissingResponse`)

| Field | Type | Description |
|---|---|---|
| `signals` | `list[Signal]` | Sorted high → medium → low severity |

**`Signal` fields:** `type`, `severity` (`"high"` \| `"medium"` \| `"low"`), `message`

Signal types and trigger conditions:

| type | severity | trigger |
|---|---|---|
| `no_context` | high | `note_count == 0` |
| `analysis_loop` | high | `investigation_count > 3 AND decision_count == 0` |
| `stale` | medium | `stale_days >= 3` |
| `low_context` | medium | `0 < note_count <= 2` |
| `no_decisions` | medium | `decision_count == 0 AND note_count > 0` |
| `lost_context` | medium | `2 <= stale_days < 3` |
| `no_model` | medium | `note_count >= 2 AND no mental_model on any note` |

### Side Effects

None. Read-only.

### Errors

- `ToolError` wrapping `ValueError` if `task_id` not found.
- `ToolError(f"TaskState missing for task {task_id}")` — `TaskState` row absent.
