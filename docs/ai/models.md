# Models — AI Fact Sheet

Source: `src/wizard/models.py`

---

## Enums

| Enum | Values |
|------|--------|
| `TaskPriority` | `low`, `medium`, `high` |
| `TaskCategory` | `issue`, `bug`, `investigation` |
| `TaskStatus` | `todo`, `in_progress`, `blocked`, `done`, `archived` |
| `MeetingCategory` | `standup`, `planning`, `retro`, `one_on_one`, `general` |
| `NoteType` | `investigation`, `decision`, `docs`, `learnings`, `session_summary`, `failure` |

---

## `TimestampMixin`

Not a table — mixed into `Task`, `Meeting`, `WizardSession`, `Note`, `TaskState`.

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `created_at` | `datetime` | `datetime.now` | No | indexed |
| `updated_at` | `datetime` | `datetime.now` | No | `onupdate=datetime.now` — ORM-level only |

**Gotchas:**
- **`onupdate` is SQLAlchemy ORM only** — raw SQL `UPDATE` statements do not refresh `updated_at`
- **`_strip_timezone` validator** runs on both fields (`mode="before"`) — strips `tzinfo` from any timezone-aware datetime so in-memory objects remain consistent with SQLite's naive datetime round-trips (pydantic v2 with `validate_default=True` converts `datetime.now()` to UTC-aware)
- `model_config = ConfigDict(validate_default=True, validate_assignment=True)`

---

## `MeetingTasks`

SQL table: `meetingtasks` (SQLModel default)
Join table for the many-to-many between `Meeting` and `Task`. No extra columns.

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `meeting_id` | `int` | — | No | FK → `meeting.id`, primary key |
| `task_id` | `int` | — | No | FK → `task.id`, primary key |

---

## `Task`

SQL table: `task`

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `id` | `int \| None` | `None` | Yes | primary key, autoincrement |
| `name` | `str` | — | No | |
| `due_date` | `datetime \| None` | `None` | Yes | |
| `priority` | `TaskPriority` | `medium` | No | |
| `category` | `TaskCategory` | `issue` | No | |
| `status` | `TaskStatus` | `todo` | No | |
| `source_id` | `str \| None` | `None` | Yes | indexed, unique; external entity identifier |
| `source_type` | `str \| None` | `None` | Yes | indexed |
| `source_url` | `str \| None` | `None` | Yes | |
| `artifact_id` | `str \| None` | `uuid4()` | Yes | indexed, unique |
| `persistence` | `str` | `"persistent"` | No | |
| `workspace` | `str \| None` | `None` | Yes | |

Inherits `created_at`, `updated_at` from `TimestampMixin`.

**Relationships:**
- `meetings: list[Meeting]` — via `MeetingTasks` join table (`back_populates="tasks"`)

---

## `Meeting`

SQL table: `meeting`

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `id` | `int \| None` | `None` | Yes | primary key, autoincrement |
| `title` | `str` | — | No | |
| `content` | `str` | — | No | |
| `category` | `MeetingCategory` | `general` | No | |
| `summary` | `str \| None` | `None` | Yes | |
| `source_id` | `str \| None` | `None` | Yes | indexed, unique; external entity identifier |
| `source_type` | `str \| None` | `None` | Yes | indexed |
| `source_url` | `str \| None` | `None` | Yes | |
| `artifact_id` | `str \| None` | `uuid4()` | Yes | indexed, unique |
| `persistence` | `str` | `"persistent"` | No | |
| `workspace` | `str \| None` | `None` | Yes | |

Inherits `created_at`, `updated_at` from `TimestampMixin`.

**Relationships:**
- `tasks: list[Task]` — via `MeetingTasks` join table (`back_populates="meetings"`)

---

## `WizardSession`

SQL table: `wizardsession` (**explicit `__tablename__`** — not the SQLModel default)

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `id` | `int \| None` | `None` | Yes | primary key, autoincrement |
| `summary` | `str \| None` | `None` | Yes | |
| `session_state` | `str \| None` | `None` | Yes | JSON-serialised `SessionState`; null until `session_end` |
| `last_active_at` | `datetime \| None` | `None` | Yes | |
| `closed_by` | `str \| None` | `None` | Yes | `'user'` / `'auto'` / `None` (open/abandoned) |
| `transcript_path` | `str \| None` | `None` | Yes | absolute path to agent transcript file |
| `agent` | `str \| None` | `None` | Yes | `'claude-code'`, `'codex'`, `'gemini'`, `'opencode'` |
| `agent_session_id` | `str \| None` | `None` | Yes | indexed; UUID assigned by agent runtime |
| `continued_from_id` | `int \| None` | `None` | Yes | indexed; wizard session ID this continues from (unclean close) |
| `active_mode` | `str \| None` | `None` | Yes | skill name of active mode, e.g. `'socratic-mentor'` |
| `is_synthesised` | `bool` | `False` | No | `True` once `Synthesiser` processed `transcript_path` |
| `artifact_id` | `str \| None` | `uuid4()` | Yes | indexed, unique |
| `persistence` | `str` | `"ephemeral"` | No | |
| `workspace` | `str \| None` | `None` | Yes | |
| `synthesis_status` | `str` | `"pending"` | No | `'pending'` \| `'complete'` \| `'partial_failure'` |
| `transcript_raw` | `str \| None` | `None` | Yes | `Text()` column; raw JSONL persisted at capture time for re-synthesis |

Inherits `created_at`, `updated_at` from `TimestampMixin`.

**Relationships:**
- `notes: list[Note]` — one-to-many (`back_populates="session"`)

**Gotchas:**
- **`synthesis_status = 'partial_failure'`** covers both partial success (some notes saved, some chunks failed) and total failure (no notes saved)
- **`session_state`** is null until `session_end` (M2); read by `resume_session` (M3)
- Re-synthesis possible via `wizard capture --close --session-id` even after agent deletes transcript file (because `transcript_raw` is persisted)

---

## `Note`

SQL table: `note`

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `id` | `int \| None` | `None` | Yes | primary key, autoincrement |
| `note_type` | `NoteType` | — | No | indexed |
| `content` | `str` | — | No | |
| `mental_model` | `str \| None` | `None` | Yes | 1-2 sentence causal abstraction; soft cap 1500 chars at display layer |
| `session_id` | `int \| None` | `None` | Yes | FK → `wizardsession.id` |
| `task_id` | `int \| None` | `None` | Yes | FK → `task.id` |
| `meeting_id` | `int \| None` | `None` | Yes | FK → `meeting.id` |
| `artifact_id` | `str \| None` | `None` | Yes | indexed; v3 identity anchor (replaces polymorphic FKs above — old FKs kept as safety net) |
| `artifact_type` | `str \| None` | `None` | Yes | `'task'` \| `'session'` \| `'meeting'` — debug only |
| `synthesis_content_hash` | `str \| None` | `None` | Yes | indexed |
| `synthesis_session_id` | `int \| None` | `None` | Yes | |
| `transcript_offset_start` | `int \| None` | `None` | Yes | |
| `transcript_offset_end` | `int \| None` | `None` | Yes | |
| `synthesis_confidence` | `float \| None` | `None` | Yes | |
| `source_note_ids` | `str \| None` | `None` | Yes | JSON array of note IDs |
| `supersedes_note_id` | `int \| None` | `None` | Yes | |
| `status` | `str` | `"active"` | No | `'active'` \| `'superseded'` \| `'contradicted'` \| `'archived'` \| `'invalid'` \| `'unclassified'` |
| `reference_count` | `int` | `0` | No | |

Inherits `created_at`, `updated_at` from `TimestampMixin`.

**Relationships:**
- `session: WizardSession \| None` — many-to-one (`back_populates="notes"`)

---

## `ToolCall`

SQL table: `toolcall` (SQLModel default)
Telemetry — **append-only, never updated**. Does not use `TimestampMixin`.

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `id` | `int \| None` | `None` | Yes | primary key, autoincrement |
| `session_id` | `int \| None` | `None` | Yes | FK → `wizardsession.id` |
| `tool_name` | `str` | — | No | |
| `called_at` | `datetime` | `datetime.now` | No | indexed |

**No `updated_at`** — `called_at` is semantically clearer than `created_at` for a log record.

---

## `PseudonymMap`

SQL table: `pseudonym_map` (**explicit `__tablename__`**)

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `id` | `int \| None` | `None` | Yes | primary key, autoincrement |
| `original_hash` | `str` | — | No | `Text()`, `unique=True`; also has named non-unique index `ix_pseudonym_map_original_hash` from migration |
| `entity_type` | `str` | — | No | `Text()` |
| `fake_value` | `str` | — | No | `Text()` |
| `created_at` | `datetime` | `datetime.now` | No | |

**Gotcha:** `unique=True` on `original_hash` emits an anonymous unique index; a separately named non-unique index (`ix_pseudonym_map_original_hash`) also exists in the DB from the migration — both coexist.

---

## `TaskState`

SQL table: `task_state` (**explicit `__tablename__`**)
Derived signals per `Task`. One-to-one with `Task`. Updated synchronously by `TaskStateRepository` on note save, status change, and task creation. **Never recomputed on read.**

| Field | Type | Default | Nullable | Notes |
|-------|------|---------|----------|-------|
| `task_id` | `int` | — | No | PK; FK → `task.id` `ON DELETE CASCADE` |
| `note_count` | `int` | `0` | No | |
| `decision_count` | `int` | `0` | No | |
| `last_note_at` | `datetime \| None` | `None` | Yes | |
| `last_status_change_at` | `datetime \| None` | `None` | Yes | |
| `last_touched_at` | `datetime` | — | No | |
| `stale_days` | `int` | `0` | No | reflects cognitive activity (notes) only — status changes do NOT reset it |
| `rolling_summary` | `str \| None` | `None` | Yes | `Text()`; synthesised overview from `mental_models`; updated on every note save; used by `task_start` for tiered context |

Inherits `created_at`, `updated_at` from `TimestampMixin`.

**Gotcha:** `stale_days` tracks cognitive activity (notes) only. Use `last_status_change_at` to distinguish administrative from cognitive activity.

---

## FTS5 Virtual Tables

Created via raw DDL in migration `a2b3c4d5e6f7` (`src/wizard/alembic/versions/a2b3c4d5e6f7_add_fts5_search_tables.py`). **Invisible to the SQLModel ORM.** Excluded from alembic autogenerate via `_include_object` in `src/wizard/alembic/env.py` (filters any table whose name ends with `_fts`, `_fts_data`, `_fts_idx`, `_fts_docsize`, or `_fts_config`).

| Virtual table | Content table | Indexed columns | Trigger set |
|---------------|---------------|-----------------|-------------|
| `note_fts` | `note` | `content` (indexed), `note_type` (UNINDEXED) | `note_fts_ai`, `note_fts_ad`, `note_fts_au` |
| `task_fts` | `task` | `name` | `task_fts_ai`, `task_fts_ad`, `task_fts_au` |
| `meeting_fts` | `meeting` | `content`, `title` | `meeting_fts_ai`, `meeting_fts_ad`, `meeting_fts_au` |
| `session_fts` | `wizardsession` | `summary` | `session_fts_ai`, `session_fts_ad`, `session_fts_au` |

- All tables use `content='<base_table>', content_rowid='id'` (content-based FTS5)
- `rowid` = entity `id` in the base table
- Triggers keep FTS index in sync with INSERT / UPDATE / DELETE on base tables
- Migration also backfills existing rows at creation time
