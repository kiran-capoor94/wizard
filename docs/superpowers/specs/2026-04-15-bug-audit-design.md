# Bug Audit & Systematic Fix — Design Spec

**Date:** 2026-04-15  
**Scope:** Full-codebase audit of confirmed bugs, logic errors, and behavioural inconsistencies  
**Approach:** Severity-gated (critical → high → medium → low), TDD throughout

---

## Context

A read-through of the wizard codebase identified 11 issues across five files. They are fixed in four severity tiers, each of which produces a commit on the `development` branch. Every fix follows Red → Green → Refactor: failing test first, then the fix, then cleanup if needed.

---

## Tier 1 — Critical (data integrity)

### Fix 1 — `ensure_daily_page` destroys non-daily pages

**File:** `src/wizard/integrations.py`  
**Location:** `NotionClient.ensure_daily_page` (~line 240)

**Bug:** The method builds `stale_ids` by collecting every child page of SISU Work that doesn't match today's title, then archives them all. Any permanent page under SISU Work (design docs, project pages, pinned notes) is archived on every `session_start`.

**Fix:**
1. Add a private helper `_is_daily_page_title(title: str) -> bool` that attempts `datetime.datetime.strptime(title, "%A %d %B %Y")` and returns `True` on success, `False` on `ValueError`.
2. In `ensure_daily_page`, only append a block to `stale_ids` if `_is_daily_page_title(block_title)` returns True. Blocks whose titles do not match the daily-page format are left completely alone.

**Tests (new):**
- Helper returns `True` for `"Wednesday 09 April 2025"`, `"Monday 01 January 2024"`.
- Helper returns `False` for `"SISU IQ Design"`, `""`, `"2024-01-01"`.
- `ensure_daily_page` with a mix of: today's daily page, an old daily page, and a permanent page — asserts only the old daily page is archived.

---

### Fix 2 — `update_task` double-commit and orphaned outcome

**File:** `src/wizard/tools.py`  
**Location:** `update_task` (~line 291–340)

**Bug:** `db.commit()` is called explicitly at line 311, inside the `get_session()` context manager (which also commits on exit). This causes a double-commit. The status change is committed to the DB before the outcome elicitation runs, meaning if elicitation times out or the process is interrupted, the outcome is silently lost while the status change is persisted.

**Fix:** Remove the explicit `db.commit()` call. The context manager's commit is the single commit point. The outcome elicitation block already sits after the flush and before the writebacks — this ordering is fine. The elicitation runs, the outcome is appended to Notion, and then the context manager commits everything local cleanly.

**Tests (new/updated):**
- Verify that when elicitation returns an outcome, `writeback().append_task_outcome` is called before the context exits.
- Verify no double-commit occurs (check that `db.commit` is not called explicitly inside the tool).

---

## Tier 2 — High (wrong outputs)

### Fix 3 — `query_compounding` matches any prior note

**File:** `src/wizard/cli/analytics.py`  
**Location:** `query_compounding` (~line 128)

**Bug:** For each `task_start` ToolCall, the function checks `select(Note).where(Note.created_at < tc.called_at).first()`. This finds *any* note from *any* task in the DB that predates the tool call. Once the database has even a single note, every subsequent task_start is counted as "compounding", making the metric always 100%.

**Fix:** A task_start is compounding if there were notes from a *prior session* (not the current reporting window's sessions). The query window's first session start time serves as the boundary. For each task_start in the window, compounding = True if any Note exists whose `session_id` belongs to a session started before the earliest session in the reporting window.

Implementation:
1. Find the earliest `WizardSession.created_at` among sessions that had a `session_start` ToolCall within the reporting window.
2. For each `task_start` ToolCall, check `Note.created_at < earliest_session_start`. Notes from before the reporting window's first session indicate prior-session context.

This is a session-boundary approximation — it doesn't require a schema change and correctly returns 0.0 for a fresh database.

**Tests (new):**
- Empty DB → `0.0`.
- DB with notes only from current window's sessions → `0.0`.
- DB with notes from a prior session, task_start in current session → `1.0`.
- Mix of compounding and non-compounding task_starts.

---

### Fix 4 — `query_tasks` counts None task_id as a task

**File:** `src/wizard/cli/analytics.py`  
**Location:** `query_tasks` (~line 89)

**Bug:** Notes without a `task_id` (session summaries, meeting notes) are included in the note query and their `None` key is inserted into `task_note_counts`. This inflates "tasks worked" by 1 and skews `avg_notes_per_task`.

**Fix:** Skip notes where `note.task_id is None`:

```python
for note in notes:
    if note.task_id is not None:
        task_note_counts[note.task_id] = task_note_counts.get(note.task_id, 0) + 1
```

**Tests (new):**
- Session with only session-summary notes (no task notes) → `worked = 0`, `avg = 0.0`.
- Mix of task notes and non-task notes → only task notes counted.

---

## Tier 3 — Medium (inconsistencies and hardcoded values)

### Fix 5 — `_check_notion_schema` hardcodes meeting category field name

**File:** `src/wizard/cli/main.py`  
**Location:** `_check_notion_schema` (~line 389)

**Bug:** `meeting_fields` contains `("Category", "multi_select")` — a hardcoded property name. If the user's schema uses a different name for the meeting category (e.g., configured via `wizard setup --reconfigure-notion`), this check always reports a failure even when the schema is correctly configured.

**Fix:** Replace `"Category"` with `schema.meeting_category`:

```python
(schema.meeting_category, "multi_select"),
```

**Tests:** Update existing `_check_notion_schema` tests to use the schema-configured name and verify the check passes.

---

### Fix 6 — `Note.mental_model` docstring contradicts behaviour

**File:** `src/wizard/models.py`  
**Location:** `Note.mental_model` field definition (~line 149)

**Bug:** The field description says `"stored as-is, not scrubbed"`, but `save_note` in `tools.py` scrubs the mental model before saving (line 202). The docstring is a lie that could mislead anyone working with the field.

**Fix:** Remove the "not scrubbed" claim from the description. Replace with an accurate description of the field's purpose and the 1500-char soft cap. The scrubbing happens at the application layer (in `save_note`), which is the correct place — the model shouldn't need to know about it.

**Tests:** No new tests needed — existing `save_note` tests cover scrubbing behaviour.

---

### Fix 7 — `task_start` returns prior notes newest-first

**File:** `src/wizard/tools.py`  
**Location:** `task_start` (~line 153)

**Bug:** `note_repo().get_for_task()` returns notes ordered `desc()` (newest first). `task_start` returns them as-is in `prior_notes`. `rewind_task` explicitly reverses to oldest-first. The convention is inconsistent — reading context oldest-first is the natural order for building understanding.

**Fix:** Reverse `prior_notes` before returning, and filter unpersisted notes (matching `rewind_task`'s existing pattern):

```python
prior_notes = [NoteDetail.from_model(n) for n in reversed(notes) if n.id is not None]
```

Update `TaskStartResponse.prior_notes` docstring: `"all notes, oldest first"`.

**Tests (new):**
- `task_start` with two notes of different timestamps returns them oldest-first.

---

### Fix 8 — `ToolCall.called_at` timezone inconsistency

**File:** `src/wizard/models.py`  
**Location:** `ToolCall.called_at` field (~line 172)

**Bug:** `called_at` uses `datetime.datetime.now(datetime.timezone.utc)` (timezone-aware). Analytics comparison boundaries use `datetime.datetime.combine(date, time.min)` (naive). SQLite stores datetimes as strings; comparing aware and naive datetime strings produces unreliable results.

**Fix:** Change `ToolCall.called_at` default factory to `datetime.datetime.now` (naive, no timezone), consistent with `TimestampMixin` behaviour and SQLite's storage model.

```python
called_at: datetime.datetime = Field(
    default_factory=datetime.datetime.now, index=True
)
```

This is not a schema change (the column type is unchanged); only the Python-layer default changes. Existing rows in production will be unaffected at query time since SQLite compares strings lexicographically and the format is the same once tz info is stripped.

**Tests (new):**
- Assert `ToolCall().called_at.tzinfo is None`.

---

### Fix 9 — `update_task` name/source_url writeback gap undocumented

**File:** `src/wizard/tools.py`  
**Location:** `update_task` docstring (~line 234)

**Bug:** The tool accepts `name` and `source_url` as updatable fields but never writes them back to Notion or Jira. The docstring's "Writebacks" section omits this, leaving callers with no indication that these fields are local-only.

**Fix:** Update the docstring to explicitly note that `name` and `source_url` are local-only (no external writeback). This is a documentation fix only — implementing name writeback to Notion is a separate feature outside this scope.

**Tests:** None — documentation-only change.

---

## Tier 4 — Low (design gaps)

### Fix 10 — `assert` statements raise `AssertionError` instead of `ToolError`

**File:** `src/wizard/tools.py`  
**Location:** `session_start`, `save_meeting_summary`, `ingest_meeting`, `create_task`

**Bug:** `assert session.id is not None`, `assert meeting.id is not None`, `assert task.id is not None`, `assert saved.id is not None` — these assertions raise `AssertionError` if they fail. The MCP host receives an unformatted error rather than a clean `ToolError` message. `assert` also gets stripped in optimised Python (`-O` flag).

**Fix:** Replace each `assert x is not None` with an explicit guard:

```python
if x is None:
    raise ToolError("Internal error: <entity> was not assigned an id after flush")
```

Cover: `session.id`, `task.id`, `meeting.id`, `saved.id` (note) in all four tools.

**Tests:** These are flush-time invariants that should never fire in practice. No new tests — the change is defensive correctness.

---

### Fix 11 — `what_am_i_missing` rules 2 and 6 produce redundant signals

**File:** `src/wizard/tools.py`  
**Location:** `what_am_i_missing` (~line 791)

**Bug:** Rule 2 fires when `stale_days >= 3` ("stale"). Rule 6 fires when `stale_days >= 2` AND `last_note_at is not None` ("lost_context"). When `stale_days >= 3`, both rules fire, producing two signals about the same staleness condition. The "lost_context" signal adds no information above rule 2 at high stale counts.

**Fix:** Add a guard to rule 6 — only fire if `sd < 3`:

```python
# Rule 6: stale 2–3 days (before rule 2's threshold takes over)
if task_state.last_note_at is not None and 2 <= sd < 3:
    signals.append(Signal(type="lost_context", ...))
```

This means "lost_context" fires in the 2–3 day window, and "stale" fires from day 3 onward. No overlap.

**Tests (new):**
- Task with `stale_days = 2` and notes → only "lost_context" fires, not "stale".
- Task with `stale_days = 3` and notes → only "stale" fires, not "lost_context".
- Task with `stale_days = 4` → only "stale" fires.

---

## Commit Strategy

Each tier lands as one commit on `development`. All tests must pass before the next tier begins. No tier bundles fixes from another tier.

| Tier | Commit message prefix | Files touched |
|------|-----------------------|---------------|
| 1 | `fix: critical —` | `integrations.py`, `tools.py` |
| 2 | `fix: analytics —` | `analytics.py` |
| 3 | `fix: medium —` | `main.py`, `models.py`, `tools.py` |
| 4 | `fix: low —` | `tools.py` |

Tests are co-committed with each fix (same commit). No separate "add tests" commits.

---

## Out of Scope

- Implementing Notion writeback for `name`/`source_url` fields (separate feature)
- `resume_session` progress reporting alignment with `session_start`
- Backfilling `ToolCall.called_at` timezone for existing rows
