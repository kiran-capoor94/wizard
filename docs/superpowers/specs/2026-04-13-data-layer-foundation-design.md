# Data Layer Foundation — Design

**Sub-project:** A (first of four milestones decomposed from the v1.1.5 blueprint)
**Target release:** v1.1.4 (auto-bumped via `feat:` commits)
**Date:** 2026-04-13
**Branch:** `feat/a-data-layer-foundation` off `main`

## Purpose

Ship the persistence-layer foundation that unblocks every downstream feature in the v1.1.5 blueprint, with **zero user-visible behaviour change** today. Three additive schema changes, one new repository, three tool-internal call-sites that update derived state synchronously. No async, no `ctx`, no new tools, no skill or prompt edits.

This release is deliberately small. Anything that could be in B+D, C, or later milestones is explicitly out of scope (see §7).

## Why now

Three blueprint features need this foundation before they can be built:

1. **`what_am_i_missing` (Milestone 3)** reads `TaskState.note_count`, `decision_count`, `stale_days`, `last_note_at`, plus a single `EXISTS(Note WHERE mental_model IS NOT NULL)` query. Cannot exist without the columns.
2. **`resume_session` (Milestone 3)** reads `WizardSession.session_state` JSON. Cannot exist without the column.
3. **`save_note` mental-model elicitation (Milestone 2)** writes to `Note.mental_model`. Cannot exist without the column.

Shipping the schema separately keeps each downstream PR small and reviewable. The migration is the only destructive path, and it is purely additive: all new columns are nullable or defaulted, and the new table is independent.

## Scope

### 1. Schema changes (one Alembic migration)

**New table — `task_state`** (one-to-one with `task`):

| Column                  | Type                       | Nullable | Notes                                                                                               |
| ----------------------- | -------------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `task_id`               | INTEGER PK FK → task.id    | NO       | `ON DELETE CASCADE`                                                                                 |
| `note_count`            | INTEGER NOT NULL DEFAULT 0 | NO       | total notes linked to this task                                                                     |
| `decision_count`        | INTEGER NOT NULL DEFAULT 0 | NO       | notes where `note_type == 'decision'`                                                               |
| `last_note_at`          | DATETIME                   | YES      | MAX(Note.created_at) for this task; null if no notes                                                |
| `last_status_change_at` | DATETIME                   | YES      | set by `update_task_status`; null until first status change post-migration                          |
| `last_touched_at`       | DATETIME NOT NULL          | NO       | `last_note_at` if notes exist, else `Task.created_at`                                               |
| `stale_days`            | INTEGER NOT NULL DEFAULT 0 | NO       | `floor((now - last_note_at) / 86400)` if notes exist, else `floor((now - Task.created_at) / 86400)` |
| `created_at`            | DATETIME NOT NULL          | NO       | indexed                                                                                             |
| `updated_at`            | DATETIME NOT NULL          | NO       | ORM `onupdate`                                                                                      |

No additional indexes — `task_id` is the PK, all other queries fan out from it.

**New column — `note.mental_model`** (TEXT NULLABLE). No length constraint at the DB level (soft cap of **1500 chars** enforced only in the application's display logic; no truncation, no validation error). Stored as-is, **not scrubbed** — mental models are short abstractions written by the engineer, not external data. The 1500-char cap is generous enough to accommodate a thorough causal abstraction without becoming a free-form note.

**New column — `wizardsession.session_state`** (TEXT NULLABLE). Holds JSON serialised from a `SessionState` Pydantic model. Null until a session is cleanly closed by a future `session_end` (Milestone 2 will start populating this). The column exists in this release so the migration is one-shot rather than two-shot.

### 2. Backfill

The migration's `upgrade()` runs the schema changes, then performs a one-time backfill of `task_state` rows for every existing `task`. Backfill uses raw SQL via `op.get_bind().execute(text(...))` rather than ORM models — this isolates the migration from any future change to `models.py` (an Alembic best practice; the migration must be replayable forever even if the models class is renamed or removed):

```python
# In upgrade(), after create_table('task_state'):
bind = op.get_bind()
now = datetime.datetime.now()
tasks = bind.execute(text("SELECT id, source_id, created_at FROM task")).fetchall()
for t in tasks:
    notes = bind.execute(text("""
        SELECT created_at, note_type FROM note
        WHERE task_id = :tid
           OR (source_id = :sid AND source_type = 'JIRA' AND :sid IS NOT NULL)
    """), {"tid": t.id, "sid": t.source_id}).fetchall()
    note_count = len(notes)
    decision_count = sum(1 for n in notes if n.note_type == 'decision')
    last_note_at = max((n.created_at for n in notes), default=None)
    last_touched = last_note_at or t.created_at
    stale = (now - last_touched).days
    bind.execute(text("""
        INSERT INTO task_state
          (task_id, note_count, decision_count, last_note_at,
           last_status_change_at, last_touched_at, stale_days,
           created_at, updated_at)
        VALUES
          (:task_id, :nc, :dc, :lna, NULL, :lt, :stale, :now, :now)
    """), {...})
```

`last_status_change_at` is left null on backfill — the column captures only changes that happen after this release ships. There is no historical log to reconstruct from.

`mental_model` and `session_state` are not backfilled — they are net-new fields and stay null on existing rows. No work needed.

### 3. Models (`src/wizard/models.py`)

- Add `TaskState(TimestampMixin, table=True)` with the columns above. Set `__tablename__ = "task_state"` explicitly — `snake_case` is the Python convention. (Existing tables `wizardsession`, `toolcall`, `meetingtasks` are pre-convention deviations; new tables follow `snake_case`. Renaming the legacy tables is tracked as future work in M4 sub-project H alongside the cascade retrofit, since both require the SQLite table-rebuild dance.) All column names also use `snake_case` (`note_count`, `decision_count`, `last_note_at`, etc.).
- PK = `task_id`, declared as `Field(foreign_key="task.id", primary_key=True, sa_column_kwargs={"ondelete": "CASCADE"})`. Cascade is at the FK level only — no ORM-level `cascade="..."` declarations.
- No `Relationship` declarations on `Task` ↔ `TaskState`. Access is always through `TaskStateRepository`, never via lazy attribute traversal. Keeping the relationship out of the model avoids accidental N+1 loads from `task.task_state` and matches the existing style for ToolCall (which also has no back-relationship on WizardSession).
- Add `mental_model: str | None = Field(default=None)` to `Note`.
- Add `session_state: str | None = Field(default=None)` to `WizardSession`.

### 4. Schemas (`src/wizard/schemas.py`)

Add the `SessionState` Pydantic model now even though no tool consumes it in this release:

```python
from typing import Literal
from pydantic import BaseModel, Field

class SessionState(BaseModel):
    intent: str
    working_set: list[int] = Field(default_factory=list)
    state_delta: str
    open_loops: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    closure_status: Literal["clean", "interrupted", "blocked"]
```

Reason for including it in A: Milestone 2 (B+D) will lift this verbatim into the `session_end` signature. Defining it here means B+D adds zero net schemas — it just imports.

`SaveNoteResponse` and `UpdateTaskStatusResponse` get one new optional field each (see §5).

### 5. Repositories (`src/wizard/repositories.py`)

Add `TaskStateRepository`:

```python
class TaskStateRepository:
    def create_for_task(self, db: Session, task: Task) -> TaskState:
        # Called from create_task tool. Initialises with zeros and stale_days
        # from task.created_at.

    def on_note_saved(self, db: Session, task_id: int) -> TaskState:
        # Called from save_note tool. Re-queries notes for the task
        # (using the same dual-lookup as NoteRepository.get_for_task),
        # recomputes note_count, decision_count, last_note_at,
        # last_touched_at, stale_days. Does NOT touch last_status_change_at.

    def on_status_changed(self, db: Session, task_id: int) -> TaskState:
        # Called from update_task_status tool. Sets last_status_change_at = now.
        # Does NOT touch any other field — status change is administrative,
        # not cognitive. stale_days specifically does not reset.

    def get_or_create(self, db: Session, task: Task) -> TaskState:
        # Defensive helper for tasks created before the migration backfilled.
        # Used internally by on_note_saved and on_status_changed.
```

All three update methods write synchronously and call `db.flush()` so the row is visible to the same transaction.

### 6. Tool wiring (`src/wizard/tools.py`)

Three tools gain one call each. No signature changes except `save_note` adds an optional last-positional/kw-compatible parameter:

**`create_task`** — After `db.add(task); db.flush()`, call `task_state_repo().create_for_task(db, task)`.

**`save_note`** — Add `mental_model: str | None = None` as the last parameter (preserves positional compatibility with the existing `task_id, note_type, content` callers). After persisting the note (and storing `mental_model` if provided), call `task_state_repo().on_note_saved(db, task_id)`.

**`update_task_status`** — Sequence inside the existing `with get_session() as db:` block:

1. Load task.
2. Update `task.status`.
3. `db.flush()`.
4. `task_state_repo().on_status_changed(db, task.id)`.
5. Jira write-back.
6. Notion write-back.

TaskState is updated **before** the external write-backs so local state is consistent even if the write-backs fail.

`save_note`'s response (`SaveNoteResponse`) gains an optional `mental_model: str | None` echo field.

`update_task_status`'s response gains a `task_state_updated: bool = True` field for telemetry-grade visibility (helpful for the future analytics CLI in Milestone 4).

**No `ctx.elicit` UX in this release.** If `mental_model` is None, it stays None. The elicitation that nudges the user comes in Milestone 2.

### 7. deps wiring (`src/wizard/deps.py`)

Add `task_state_repo()` as an `lru_cache` singleton matching the existing repository pattern.

### 8. Tests

**`tests/test_repositories.py`** (extend):

- `TaskStateRepository.create_for_task` produces zeros, `last_note_at=None`, `stale_days` reflecting `task.created_at`.
- `on_note_saved` increments `note_count`, leaves `decision_count` at 0 for non-decision notes, increments it for decision notes.
- `on_note_saved` sets `last_note_at` to the most recent note's `created_at`, and recomputes `stale_days` from that.
- `on_note_saved` does **not** modify `last_status_change_at`.
- `on_status_changed` sets `last_status_change_at` and leaves every other field unchanged.
- Dual-lookup: `on_note_saved` for a task with `source_id` finds notes anchored by Jira key as well as by `task_id`.

**`tests/test_tools.py`** (extend):

- `create_task` returns a response and a corresponding `task_state` row exists with `note_count == 0`.
- `save_note` with `mental_model="..."` stores it on the Note and updates `task_state`.
- `save_note` without `mental_model` still updates `task_state`, leaves Note.mental_model as null.
- `update_task_status` updates `task_state.last_status_change_at` but not `stale_days`.

**`tests/test_models.py`** (extend):

- `SessionState.model_validate({...})` round-trips correctly with all six fields.
- `closure_status` rejects values outside the literal set.

**Migration smoke test** (new — `tests/test_migration_data_layer.py`):

- Use the existing `tests/conftest.py` engine fixture or create a scratch engine.
- Apply migrations up to the previous head (`15146de1d71a`), seed two tasks (one with notes including a decision, one without), apply this new migration, then assert: a `task_state` row exists for each task with the correct backfilled `note_count`, `decision_count`, `last_note_at`, `stale_days`.
- Apply `downgrade()` and assert the table and columns are gone.

### 9. Migration name

`<hash>_add_task_state_mental_model_session_state.py`. Down-revision = `15146de1d71a`.

## Non-goals (explicit)

| Out of scope here                                                     | Lands in                                                                                        |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Async tools, `ctx: Context` injection                                 | Milestone 2 (B+D)                                                                               |
| `ctx.elicit` mental-model nudge in `save_note`                        | Milestone 2 (B+D)                                                                               |
| `ctx.elicit` outcome summary in `update_task_status` when status=done | Milestone 2 (B+D)                                                                               |
| `session_end` six-field signature                                     | Milestone 2 (B+D)                                                                               |
| `rewind_task`, `what_am_i_missing`, `resume_session` tools            | Milestone 3 (C)                                                                                 |
| Notion schema discovery                                               | Milestone 4 (E)                                                                                 |
| Multi-agent setup, `--agent` flag                                     | Milestone 4 (F)                                                                                 |
| `wizard analytics` CLI                                                | Milestone 4 (G)                                                                                 |
| Skill / prompt wording changes                                        | Milestone 4 (H)                                                                                 |
| `latest_mental_model` field on `TaskStartResponse`                    | Milestone 2 — needs the column to exist (this release) and `task_start` to surface it (M2 work) |

## Blast radius

**Files touched:**

- `src/wizard/models.py` — three additions
- `src/wizard/schemas.py` — `SessionState` model + two response field additions
- `src/wizard/repositories.py` — `TaskStateRepository` class
- `src/wizard/deps.py` — one `lru_cache` factory
- `src/wizard/tools.py` — three tool bodies, `save_note` signature
- `alembic/versions/<hash>_add_task_state_mental_model_session_state.py` — new file
- `tests/test_repositories.py`, `tests/test_tools.py`, `tests/test_models.py`, `tests/test_migration_data_layer.py`

**Files NOT touched:**

- `src/wizard/services.py`, `integrations.py`, `security.py`, `prompts.py`, `resources.py`, `mcp_instance.py`, `mcp_config.py`, `database.py`, `config.py`, `mappers.py`
- All skill files
- All CLI commands

**What breaks if wrong:**

- Migration: only destructive path. Mitigation: all additions are nullable or defaulted; backfill is computed from existing data; migration test verifies upgrade + downgrade on a seeded DB.
- `save_note` signature change: kw-only optional parameter, fully backwards-compatible. Existing callers that pass three positional args still work.
- Tool wiring: `TaskStateRepository.get_or_create` defends against any task that somehow lacks a paired row (e.g. created mid-migration), so the new code is safe even on the gap window between deploy and backfill completion.

## Release plan

- Branch: `feat/a-data-layer-foundation` from `main` (currently at v1.1.3).
- TDD per global rules: write tests first per checkpoint in the implementation plan.
- Commits prefixed `feat:` for the schema and repository (triggers minor → v1.1.4). Tests and docs use `test:` / `docs:`.
- PR title: `feat: data layer foundation — TaskState, mental_model, session_state`.
- Verification before PR: `pytest`, manual `alembic upgrade head` + `alembic downgrade -1` on a copy of `wizard.db`, `wizard doctor` against the migrated DB.
- Code-reviewer agent before merge.

## Reviewer decisions (2026-04-13)

| #   | Decision                                                                                                                                                                                                               |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `last_status_change_at` left null on backfill — no historical reconstruction.                                                                                                                                          |
| 2   | `mental_model` soft cap **1500 chars** at the application display layer; no DB constraint.                                                                                                                             |
| 3   | `session_state` stored as TEXT, parsed via Pydantic at the application layer.                                                                                                                                          |
| 4   | `task_state.task_id` uses `ON DELETE CASCADE`. **Policy going forward:** all new FK columns must declare `ON DELETE CASCADE` unless an explicit reason to do otherwise is documented in the spec that introduces them. |

### Cascade policy — implications

The new policy ("all on deletes should cascade unless set explicitly") applies to **new** FKs added from this release onward. Existing FKs (`Note.session_id`, `Note.task_id`, `Note.meeting_id`, `ToolCall.session_id`, `MeetingTasks.*`) currently have no `ON DELETE` action — they are bare FKs.

**Decision for sub-project A:** do **not** retrofit cascade onto existing FKs in this release. Reasons:

- SQLite cannot `ALTER` an FK constraint — retrofitting requires the table-rebuild dance (rename old, create new, copy data, drop old, rename new) for each affected table. Substantial separate migration with its own blast radius.
- No code path in the current codebase deletes rows from `task`, `meeting`, or `wizardsession`, so existing bare FKs are not actively wrong today — only inconsistent with the new policy.
- Mixing the policy retrofit into A would inflate the diff and dilute the data-layer intent.

**Tracked as a follow-up** for Milestone 4 polish (sub-project H): one focused migration to retrofit cascade onto all existing FKs. Will be added to the v1.1.5 decomposition memory and surfaced when M4 is brainstormed.
