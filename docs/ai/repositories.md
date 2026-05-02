# repositories — AI Fact Sheet

Source: `src/wizard/repositories/` (package)  
Public re-exports via `__init__.py`: `MeetingRepository`, `NoteRepository`, `SearchRepository`, `SessionRepository`, `TaskRepository`, `TaskStateRepository`, `build_rolling_summary`, `find_latest_session_with_notes`

---

## `AnalyticsRepository`

**Source:** `src/wizard/repositories/analytics.py`  
**Constructor:** no-arg (stateless — no shared state, instantiated fresh per caller)

| Method | Args | Returns | Description |
|---|---|---|---|
| `get_session_stats` | `db, start: date, end: date` | `dict` | Aggregate session counts, avg duration (minutes), tool call totals, abandoned rate, synthesis failure IDs, pending synthesis count |
| `get_note_stats` | `db, start: date, end: date` | `dict` | Note counts by type, mental model coverage ratio, unclassified/superseded counts |
| `get_task_stats` | `db, start: date, end: date` | `dict` | Tasks worked, avg notes/task, stale task count (stale_days > 3, status todo/in_progress) |
| `get_compounding_score` | `db, start: date, end: date` | `float` | Fraction of `task_start` tool calls where prior notes already existed |
| `get_note_velocity` | `db, start: date, end: date` | `dict[str, int]` | `{iso_date: note_count}` per day in range; missing days filled with 0 |
| `get_session_velocity` | `db, start: date, end: date` | `dict[str, float]` | `{iso_date: avg_duration_minutes}` per day; missing days filled with 0.0 |
| `get_tool_call_frequency` | `db, days: int` | `dict[str, int]` | `{tool_name: call_count}` for last N days, ordered by frequency desc |

**Key query patterns:**
- `get_session_stats`: single `GROUP BY closed_by` query to avoid a full scan; `JULIANDAY` diff × 1440 for minutes.
- `get_compounding_score`: session `created_at` keyed into a dict for O(1) lookup inside the `task_start` loop; earliest note fetched once outside the loop.
- `get_task_stats`: `TaskState JOIN Task` with `in_()` filter on status — no per-task queries.

**Invariants:**
- **All aggregation happens in SQLite — no full-table-scan-into-Python.** Aggregate functions (`COUNT`, `AVG`, `MAX`) pushed to the DB.
- `abandoned_rate` uses `session_count` denominator; returns 0.0 if no sessions.
- Duration formula: `closed_by in ("user","hook")` → `updated_at`; `"auto"` → `last_active_at`; open sessions excluded.

---

## `MeetingRepository`

**Source:** `src/wizard/repositories/meeting.py`  
**Constructor:** no-arg

| Method | Args | Returns | Description |
|---|---|---|---|
| `get_by_source_id` | `db, source_id: str` | `Meeting \| None` | Lookup by external source identifier |
| `get_by_id` | `db, meeting_id: int` | `Meeting` | Lookup by PK; raises `ValueError` if not found |
| `get_unsummarised_contexts` | `db` | `list[MeetingContext]` | All meetings where `summary IS NULL`; maps to `MeetingContext` schema |
| `save` | `db, meeting: Meeting` | `Meeting` | `db.add` + `flush` + `refresh`; returns persisted row |
| `link_tasks` | `db, meeting_id: int, task_ids: list[int]` | `None` | Creates `MeetingTasks` join rows, skipping duplicates |

**Key query patterns:**
- `link_tasks`: batch-loads existing `MeetingTasks` with `.in_(task_ids)` into a set before the insert loop — avoids N duplicate-check queries.

**Invariants:**
- **Never call `get_by_id` inside a loop** — use `get_by_source_id` or batch-load.
- `get_unsummarised_contexts` raises `ValueError` if a `Meeting` row has `id=None`.

---

## `NoteRepository`

**Source:** `src/wizard/repositories/note.py`  
**Constructor:** no-arg

| Method | Args | Returns | Description |
|---|---|---|---|
| `save` | `db, note: Note` | `Note` | Persist a Note row |
| `get_by_content_hash` | `db, task_id: int, content_hash: str` | `Note \| None` | First active note matching `task_id` + `synthesis_content_hash` |
| `get_for_task` | `db, task_id: int \| None, ascending=False, limit=None` | `list[Note]` | All notes for a task, ordered by `created_at` |
| `get_notes_grouped_by_task` | `db, session_id: int` | `dict[int, list[Note]]` | Single query; groups by `task_id` in Python — O(N) pass |
| `count_investigations` | `db, task_id: int` | `int` | Count of `NoteType.INVESTIGATION` notes for a task |
| `has_mental_model` | `db, task_id: int` | `bool` | True if any note on task has `mental_model IS NOT NULL` |
| `list_for_session` | `db, session_id: int` | `list[Note]` | All notes for a session, ascending by `created_at` |
| `count_for_session` | `db, session_id: int` | `int` | Note count for a session |
| `get_notes_by_artifact_id` | `db, artifact_id: str, ascending=False, limit=None` | `list[Note]` | Notes by `artifact_id`, ordered by `created_at` |
| `get_artifact_id_hashes` | `db, artifact_id: str` | `set[str]` | All non-null `synthesis_content_hash` values for an artifact |
| `get_recent` | `db, days: int` | `list[Note]` | Active notes from last N days, newest first |
| `count_for_sessions` | `db, session_ids: list[int]` | `dict[int, int]` | Batch note count per session; `{session_id: count}` |

**Key query patterns:**
- `count_for_sessions`: single `GROUP BY session_id` query with `.in_(session_ids)` — batch load, never call `count_for_session` inside a loop.
- `get_notes_grouped_by_task`: one query for all session notes, single-pass Python grouping — O(N) not O(N×tasks).
- `get_artifact_id_hashes`: projects only the hash column to avoid loading full Note objects.

**Invariants:**
- **`get_for_task` returns `[]` immediately if `task_id is None`** — safe to call before task assignment.
- `get_by_content_hash` filters `status == "active"` — superseded/archived notes not matched.
- `build_rolling_summary` (module-level function, not a method): filters `status in ("active", None)`, requires `mental_model` set, returns `None` if no qualifying notes.

---

## `SearchRepository`

**Source:** `src/wizard/repositories/search.py`  
**Constructor:** no-arg

| Method | Args | Returns | Description |
|---|---|---|---|
| `search` | `db, query: str, limit=10, entity_type: EntityType \| None` | `list[SearchResult]` | Fan-out FTS5 search; merges and sorts by rank |

`EntityType = Literal["note", "session", "meeting", "task"]`

**Key query patterns:**
- FTS5 tables: `note_fts`, `session_fts`, `meeting_fts`, `task_fts`
- Query sanitisation: strips `"` and `*`, wraps result in double-quotes (`"phrase"`) so FTS5 treats hyphens and special chars literally.
- Each FTS5 query uses `WHERE <table> MATCH :q ORDER BY <table>.rank LIMIT :lim`.
- Results joined to the source table (`JOIN note ON note.id = note_fts.rowid`) to retrieve `created_at`, `task_id`, etc.
- Merge: all results collected as `list[tuple[float, SearchResult]]`; sorted by FTS5 `rank` ascending (lower = better match); top `limit` returned.
- `entity_type` filter: if set, only the matching FTS table is queried.

**Invariants:**
- **Uses raw `sqlalchemy.text()` for FTS5 queries — SQLModel ORM cannot express FTS5 MATCH syntax.**
- Empty/whitespace-only query returns `[]` without hitting the DB.
- Snippet truncated to 200 chars from `content`/`summary` columns.

---

## `SessionRepository`

**Source:** `src/wizard/repositories/session.py`  
**Constructor:** no-arg

| Method | Args | Returns | Description |
|---|---|---|---|
| `list_paginated` | `db, closure_status_filter: str \| None, limit=20, offset=0` | `list[WizardSession]` | Paginated sessions, newest first; optional `closed_by` filter |
| `count` | `db, closure_status_filter: str \| None` | `int` | Total session count, optional `closed_by` filter |
| `count_today` | `db` | `int` | Sessions created today (local time, since midnight) |
| `get` | `db, session_id: int` | `WizardSession \| None` | Session by PK; returns None if not found |
| `get_prior_summaries` | `db, current_session_id: int` | `list[PriorSessionSummary]` | 3 most recent closed sessions with summaries, excluding current |
| `get_most_recent_id` | `db` | `int \| None` | PK of most recently created session |
| `set_active_mode` | `db, session_id: int, mode: str \| None` | `WizardSession` | Sets `active_mode`, flushes; raises `ValueError` if not found |

**Module-level function:**

| Function | Args | Returns | Description |
|---|---|---|---|
| `find_latest_session_with_notes` | `db` | `WizardSession \| None` | Most recent session that has at least one Note (correlated EXISTS subquery) |

**Key query patterns:**
- `get_prior_summaries`: `WHERE summary IS NOT NULL AND id != current_session_id ORDER BY created_at DESC LIMIT 3`.
- `get_most_recent_id`: projects only `id` column, `ORDER BY created_at DESC, id DESC LIMIT 1`.

**Invariants:**
- `get_prior_summaries` returns at most 3 entries — used for session continuity context.
- `closed_by` values: `"user"`, `"hook"`, `"auto"`, `NULL` (open/abandoned).

---

## `TaskRepository`

**Source:** `src/wizard/repositories/task.py`  
**Constructor:** no-arg

| Method | Args | Returns | Description |
|---|---|---|---|
| `get` | `db, task_id: int` | `Task \| None` | Nullable PK lookup |
| `get_by_id` | `db, task_id: int` | `Task` | Raises `ValueError` if not found |
| `save` | `db, task: Task` | `Task` | Persist task; flush + refresh |
| `list_paginated` | `db, status_filter: list[str] \| None, source_type_filter: str \| None, limit=50, offset=0` | `list[Task]` | Paginated; `.in_()` for status filter |
| `get_by_source_id` | `db, source_id: str` | `Task \| None` | Lookup by external identifier |
| `upsert_by_source_id` | `db, source_id, name, priority, source_url` | `Task \| None` | Update existing task if found and not done/archived; returns None if absent or terminal |
| `get_active_task_names` | `db` | `list[str]` | Names of all non-done, non-archived tasks |
| `get_by_name` | `db, name: str` | `Task \| None` | First exact name match |
| `get_names_by_ids` | `db, task_ids: list[int]` | `list[str]` | Batch name lookup; preserves input order |
| `get_open_task_contexts` | `db, limit: int \| None` | `list[TaskContext]` | TODO + IN_PROGRESS tasks as `TaskContext`; for MCP resources |
| `get_blocked_task_contexts` | `db, limit: int \| None` | `list[TaskContext]` | BLOCKED tasks as `TaskContext`; for MCP resources |
| `get_workable_task_contexts` | `db, include_blocked=False, limit: int \| None` | `list[TaskContext]` | Open tasks; optionally includes BLOCKED |
| `count_open_tasks` | `db` | `int` | Count of TODO + IN_PROGRESS tasks |
| `get_open_tasks_compact` | `db, limit=40` | `list[tuple[int, str]]` | `(id, name)` pairs for open tasks, sorted by priority; used by synthesis |
| `get_task_context` | `db, task: Task` | `TaskContext` | Build `TaskContext` for a known task (fetches state + latest note) |
| `get_task_contexts_by_ids` | `db, task_ids: list[int]` | `list[TaskContext]` | Batch-load Tasks, TaskStates, latest notes for a set of IDs |
| `get_open_task_index` | `db, limit: int \| None` | `list[TaskIndexEntry]` | Compact index for `session_start`; sorted by `_score_open_task` desc |
| `get_blocked_task_index` | `db, limit: int \| None` | `list[TaskIndexEntry]` | Compact index of blocked tasks; sorted by `stale_days` desc |

**Key query patterns:**
- **`_load_task_scaffolding`** (private): single query with correlated scalar subquery (`MAX(Note.created_at)` per task) for `last_worked_at`; then two batch loads:
  - `TaskState` via `.in_(task_ids)` → `dict[int, TaskState]`
  - `_batch_load_latest_notes` via `.in_(task_ids)` → `dict[int, Note]`
- **`_batch_load_latest_notes`**: single query ordered by `created_at DESC`; Python de-duplication keeps first (latest) per `task_id` — **never calls `db.get()` per task**.
- **`_batch_load_notes_by_type`**: `GROUP BY task_id, note_type` with `.in_(task_ids)` → nested dict; used by `_query_task_index` to compute `notes_by_type` counts.
- **`get_names_by_ids`**: `.in_(task_ids)` query → dict for O(1) lookup; preserves input order.
- **`get_task_contexts_by_ids`**: three separate batch queries (Tasks, TaskStates, notes), each with `.in_(task_ids)`.

**Priority ordering:** module-level `_PRIORITY_ORDER` CASE expression: HIGH=0, MEDIUM=1, else=2.

**Scoring (`_score_open_task`, module-level):** +40 stale_days==0, +30 IN_PROGRESS, +15 has decision note, +15 note_count≥3. Used by `get_open_task_index`.

**Invariants:**
- **Never call `get` or `get_by_id` in a loop** — use `get_task_contexts_by_ids` or `_load_task_scaffolding`.
- `get_open_task_contexts` is for MCP resources; `get_open_task_index` is for `session_start` (different schema: `TaskContext` vs `TaskIndexEntry`).
- `upsert_by_source_id` does NOT create new tasks; returns `None` if absent.
- `get` vs `get_by_id`: `get` returns `None`; `get_by_id` raises on miss.

---

## `TaskStateRepository`

**Source:** `src/wizard/repositories/task_state.py`  
**Constructor:** no-arg

Class docstring: *"Pre-computes derived signals per Task. Updated synchronously by `create_task` / `save_note` / `update_task` tools — never lazily on read. `stale_days` is computed at write time and stored. Status changes do NOT reset `stale_days`; only cognitive activity (note saves) advances it."*

| Method | Args | Returns | Description |
|---|---|---|---|
| `create_for_task` | `db, task: Task` | `TaskState` | Insert fresh `TaskState` row; all counts zero; `stale_days = (now - task.created_at).days` |
| `on_note_saved` | `db, task_id, note_type, note_created_at=None` | `TaskState` | Increments `note_count` (and `decision_count` if DECISION); sets `stale_days=0`; rebuilds `rolling_summary` from mental_model notes only |
| `recompute_for_task` | `db, task_id: int` | `TaskState` | Full recompute from DB (used post-synthesis); queries total/decision counts, `MAX(created_at)`, and mental_model notes |
| `update_rolling_summary` | `db, task_id: int, summary: str` | `None` | Overwrites `rolling_summary` only; used by synthesis after transcript processing |
| `on_status_changed` | `db, task_id: int` | `TaskState` | Sets `last_status_change_at = now`; **does not touch `stale_days`** |
| `refresh_stale_days` | `db` | `None` | Bulk UPDATE all `TaskState.stale_days` using `julianday("now") - julianday(last_touched_at)`; called at `session_start` |
| `get_for_tasks` | `db, task_ids: list[int]` | `list[TaskState]` | Batch load TaskStates via `.in_(task_ids)` |
| `get_by_task_id` | `db, task_id: int` | `TaskState \| None` | Single PK lookup |

**Key query patterns:**
- `refresh_stale_days`: **single bulk `UPDATE` via SQLAlchemy `update()` + `julianday`** — avoids loading all rows into Python.
- `on_note_saved`: targeted query for only mental_model-bearing notes (`WHERE mental_model IS NOT NULL`) — does not re-query all notes for a task.
- `recompute_for_task`: two aggregate queries (`COUNT + MAX`, then `COUNT` for decisions) rather than loading all notes.
- `get_for_tasks`: `.in_(task_ids)` batch load — **never call `get_by_task_id` in a loop**.

**Invariants:**
- **`stale_days` resets to 0 only on `on_note_saved`** — status changes leave it unchanged.
- `create_for_task` requires `task.id is not None` (task must be flushed first).
- `_get_or_create` (private): defensive helper that creates a zero-count `TaskState` if missing; logs a warning. Used by `on_note_saved` and `on_status_changed` to handle pre-migration tasks.
- `refresh_stale_days` called at `session_start` so `what_am_i_missing` sees current staleness rather than the value frozen at last note-save.
