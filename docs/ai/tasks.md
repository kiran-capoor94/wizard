# tasks.md — AI fact sheet

## Task enum values

**`TaskStatus`**

| Value | Notes |
|---|---|
| `todo` | Default status |
| `in_progress` | |
| `blocked` | Excluded from `what_should_i_work_on` in `focus`/`quick-wins` modes |
| `done` | Requires `elicit_done_confirmation()` via `update_task` |
| `archived` | |

**`TaskPriority`**

| Value |
|---|
| `low` |
| `medium` (default) |
| `high` |

**`TaskCategory`**

| Value |
|---|
| `issue` (default) |
| `bug` |
| `investigation` |

**Status aliases** — accepted by `create_task` and `update_task` via `_normalize_status()`

| Alias | Resolves to |
|---|---|
| `completed` | `done` |
| `complete` | `done` |
| `finish` | `done` |
| `finished` | `done` |
| `open` | `todo` |
| `pending` | `todo` |
| `wip` | `in_progress` |
| `doing` | `in_progress` |
| `inactive` | `archived` |

---

## `TaskState` fields

One-to-one with `Task`. Updated synchronously by `TaskStateRepository` on note save, status change, and task creation. **Never recomputed on read.**

| Field | Type | Notes |
|---|---|---|
| `task_id` | `int` | FK to `task.id`, primary key, CASCADE delete |
| `note_count` | `int` | Total notes saved for this task |
| `decision_count` | `int` | Count of `NoteType.DECISION` notes |
| `last_note_at` | `datetime \| None` | Timestamp of most recent note save |
| `last_status_change_at` | `datetime \| None` | Timestamp of most recent status update |
| `last_touched_at` | `datetime` | Set at creation; updated on note save or status change |
| `stale_days` | `int` | Days since last note (not status change); see staleness logic |
| `rolling_summary` | `str \| None` | Built from `mental_model` fields; see rolling_summary section |

---

## Staleness logic

- **`stale_days`** = days since the last **note** was saved (`last_note_at`)
- Status changes (via `update_task`) do **not** reset `stale_days`
- `last_status_change_at` tracks administrative changes independently
- **`refresh_stale_days()`** is called at every `session_start` to bulk-update `stale_days` for all tasks

**Design intent**: `stale_days` measures cognitive activity (notes), not administrative housekeeping (status changes). A task marked `in_progress` without any notes still accrues stale days.

---

## `rolling_summary`

- Built from the `mental_model` fields of all prior notes for the task
- Updated on every `save_note` call (via `TaskStateRepository.on_note_saved`)
- Used by `task_start` for tiered context delivery — surfaced in `TaskStartResponse.rolling_summary`
- **`null` until at least one note with a non-null `mental_model` is saved**

---

## `NoteType` values

| Value | Meaning |
|---|---|
| `investigation` | Findings, exploration, research |
| `decision` | Resolved choices; always load-bearing context in `task_start` |
| `docs` | How things work |
| `learnings` | Surprises, corrections |
| `session_summary` | Written by `session_end` and `SessionCloser`; not agent-authored |
| `failure` | What didn't work; highest priority tier in `task_start` note selection |

---

## Note compression in `save_note`

| Condition | Behaviour |
|---|---|
| `len(content) > 100_000` | Raises `ToolError("Content exceeds 100k character limit")` — hard limit |
| `len(content) > 1000` | Calls `_compress_note_content()` via `ctx.sample()` — LLM compression to <1000 chars |
| `len(mental_model) > 1000` | Same compression applied to `mental_model` field |

**`_compress_note_content()` prompt contract**: preserve all file paths, function names, line numbers, error messages, decisions, and technical specifics exactly; remove filler and redundant phrasing only. Output truncated to 1000 chars if LLM returns more.

**Note deduplication**: SHA-256 hash of clean content stored as `synthesis_content_hash`. Duplicate detected via `NoteRepository.get_by_content_hash()`. If duplicate exists and new note has a `mental_model` but existing does not, the `mental_model` is patched onto the existing note; `SaveNoteResponse.was_duplicate = True` returned.

---

## `task_start` outputs — `TaskStartResponse`

| Field | Type | Notes |
|---|---|---|
| `task` | `TaskContext` | Full task context including status, priority, stale_days, counts |
| `notes_by_type` | `dict[str, int]` | e.g. `{"investigation": 3, "decision": 1}` |
| `prior_notes` | `list[NoteDetail]` | Up to 5 key notes; see tiered selection below |
| `latest_mental_model` | `str \| None` | Most recent non-null `mental_model` across all notes |
| `rolling_summary` | `str \| None` | From `TaskState.rolling_summary`; `null` until first mental_model note |
| `total_notes` | `int` | Total note count including notes not returned |
| `older_notes_available` | `bool` | `True` if `total_notes > len(prior_notes)`; use `rewind_task` for full history |
| `compounding` | `bool` | `True` if `total_notes > 0` |
| `skill_instructions` | `str \| None` | Loaded from `SKILL_TASK_START`; sent only on **first** `task_start` call per session |

**Note selection tiers** (priority order, total capped at 5):

| Tier | Content | Order within tier |
|---|---|---|
| 0 | All `failure` notes | Oldest first |
| 1 | All `decision` notes | Oldest first |
| 2 | Notes with `mental_model` set | Oldest first |
| 3 | Most recent notes (fill to cap) | Newest first |

---

## `create_task` deduplication

- **`source_id`** has a `UNIQUE` constraint in the DB
- If `source_id` is provided: calls `t_repo.upsert_by_source_id()` — returns existing task if found, sets `already_existed=True`
- **Safe to call every session without creating duplicates** when `source_id` is stable

---

## Elicitation in task tools

Both functions use `ctx.elicit()` and **degrade gracefully** when transport does not support elicitation (catches `Exception`, logs at `DEBUG`, applies safe default).

### `check_duplicate_name()` — `task_fields.py`

- Triggered when `source_id` is absent and a fuzzy name match exists in active tasks
- Match condition: `name.lower() in existing.lower()` or `existing.lower() in name.lower()`
- Prompts: `"A task named {matching!r} already exists. Create anyway?"`
- Response type: `_ConfirmCreate(create_anyway: bool)`
- Returns existing task name to block creation, or `None` to proceed
- **Default if unavailable**: proceeds with creation (`return None`)

### `elicit_done_confirmation()` — `task_fields.py`

- Triggered when `update_task` receives `status = "done"`
- Prompts: `"Mark {task_name!r} as done? This closes the task."`
- Response type: `_ConfirmDone(confirmed: bool)`
- Returns `False` → `UpdateTaskResponse(updated_fields=[], task_state_updated=False)` (no-op)
- **Default if unavailable**: proceeds with status change (`return True`)

---

## `what_should_i_work_on` scoring modes

**Scoring formula**: `priority_score * w_priority + recency_score * w_recency + momentum_score * w_momentum + simplicity_score * w_simplicity`

| Score component | Calculation |
|---|---|
| `priority_score` | `high=1.0`, `medium=0.5`, `low=0.2` |
| `recency_score` | `1.0 / (1.0 + stale_days)` |
| `momentum_score` | `min(note_count / 10.0, 1.0)` — saturates at 10 notes |
| `simplicity_score` | `1.0 - min(note_count / 20, 1.0)` — inverse of note_count |

**Mode weights**

| Mode | `priority` | `recency` | `momentum` | `simplicity` | Task filter |
|---|---|---|---|---|---|
| `focus` | 0.50 | 0.30 | 0.20 | 0.00 | Non-blocked only |
| `quick-wins` | 0.20 | 0.15 | 0.15 | 0.50 | Non-blocked only |
| `unblock` | 0.40 | 0.40 | 0.20 | 0.00 | Blocked tasks only |

**`focus`**: Maximises priority and recency — surfaces the highest-priority tasks that have been touched recently. Best for deep work sessions.

**`quick-wins`**: Maximises simplicity (low note_count = less complex). Surfaces low-investment tasks that can be completed quickly. Priority is de-emphasised.

**`unblock`**: Filters to `blocked` tasks only; balances priority and recency to surface the most overdue blocked items.

**`time_budget` adjustments** (when `time_budget="30m"`):
- `in_progress` tasks: `score += 0.1`
- Tasks with zero notes: `score -= 0.1`

**LLM reasons**: Sampled for top 4 candidates only (`_MAX_SAMPLE_COUNT = 4`). Falls back to `_fallback_reason()` if sampling unavailable.

**Momentum classification**

| Value | Condition |
|---|---|
| `new` | `note_count == 0` |
| `active` | `stale_days <= 2` |
| `cooling` | `stale_days <= 7` |
| `cold` | `stale_days > 7` |
