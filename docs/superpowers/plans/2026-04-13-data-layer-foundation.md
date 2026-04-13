# Data Layer Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the schema + repository foundation that unblocks every downstream feature in the v1.1.5 blueprint, with zero user-visible behaviour change today.

**Architecture:** One additive Alembic migration (new `task_state` table + `note.mental_model` column + `wizardsession.session_state` column, with backfill from existing notes). One new `TaskStateRepository` with synchronous create/update paths. Three existing tools (`create_task`, `save_note`, `update_task_status`) gain one repository call each. `save_note` accepts an optional last-positional `mental_model` parameter. No async, no FastMCP `Context`, no new tools, no skill or prompt edits.

**Tech Stack:** Python 3.14, SQLite, SQLModel + Alembic, Pydantic v2, FastMCP (existing tools stay synchronous in this release), pytest, respx (already in test deps).

**Spec:** `docs/superpowers/specs/2026-04-13-data-layer-foundation-design.md`

**Branch:** `feat/a-data-layer-foundation` off `main` at `a902322` (v1.1.3).

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `src/wizard/models.py` | Modify | Add `TaskState` class, `mental_model` field on `Note`, `session_state` field on `WizardSession` |
| `src/wizard/schemas.py` | Modify | Add `SessionState` Pydantic model; extend `SaveNoteResponse` and `UpdateTaskStatusResponse` |
| `src/wizard/repositories.py` | Modify | Add `TaskStateRepository` |
| `src/wizard/deps.py` | Modify | Add `task_state_repo()` `lru_cache` factory |
| `src/wizard/tools.py` | Modify | Wire `TaskStateRepository` calls into `create_task`, `save_note`, `update_task_status`; add `mental_model` param to `save_note` |
| `alembic/versions/<hash>_add_task_state_mental_model_session_state.py` | Create | One migration covering all three schema changes plus backfill |
| `tests/test_models.py` | Modify | Cover `TaskState` model, `Note.mental_model`, `WizardSession.session_state`, `SessionState` Pydantic |
| `tests/test_repositories.py` | Modify | Cover all four `TaskStateRepository` methods |
| `tests/test_tools.py` | Modify | Cover updated `create_task`, `save_note`, `update_task_status` |
| `tests/test_migration_data_layer.py` | Create | Migration smoke test (upgrade + downgrade + backfill correctness) |

---

## Conventions used throughout this plan

- **TDD red → green → refactor.** Every code task starts with a failing test and only adds enough implementation to pass it.
- **Test fixture.** `tests/conftest.py` provides an autouse `db_session` fixture that creates a fresh in-memory SQLite engine per test and applies `SQLModel.metadata.create_all`. New tests use the same fixture. `tests/helpers.py::mock_session(db_session)` returns a context-manager replacement for `get_session()` used by tool tests.
- **Imports.** Follow the existing import order (`stdlib`, `third-party`, `.local`). Use absolute `from .module import name` style as in `tools.py`.
- **Logging.** Match existing pattern: `logger = logging.getLogger(__name__)` at module top, `logger.info(...)` / `logger.warning(...)` only.
- **Commit cadence.** One commit per task. Use `feat:` for the schema, repository, and tool wiring (triggers minor bump → v1.1.4); `test:` for test-only commits.
- **Verification before commit.** Run the specific test(s) for the task plus `pytest -x tests/` to ensure no regression.

---

## Task 1: Add `SessionState` Pydantic schema

**Files:**
- Modify: `src/wizard/schemas.py` (add new class near top after imports)
- Test: `tests/test_models.py` (add new `class TestSessionState:` block)

**Why first:** zero dependencies, exercises the test infrastructure, sets up the import path for future milestones without touching SQL.

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from wizard.schemas import SessionState


class TestSessionState:
    def test_round_trip_with_all_six_fields(self):
        data = {
            "intent": "Progress ADRs to decision",
            "working_set": [40, 39],
            "state_delta": "ADR 005 accepted. ADR 007 reframed.",
            "open_loops": ["ADR changes not committed"],
            "next_actions": ["Commit ADR 005 + 007"],
            "closure_status": "interrupted",
        }
        state = SessionState.model_validate(data)
        assert state.intent == data["intent"]
        assert state.working_set == [40, 39]
        assert state.closure_status == "interrupted"
        assert state.model_dump() == data

    def test_default_lists_are_empty(self):
        state = SessionState.model_validate(
            {"intent": "x", "state_delta": "y", "closure_status": "clean"}
        )
        assert state.working_set == []
        assert state.open_loops == []
        assert state.next_actions == []

    def test_closure_status_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            SessionState.model_validate(
                {"intent": "x", "state_delta": "y", "closure_status": "paused"}
            )

    def test_intent_required(self):
        with pytest.raises(ValidationError):
            SessionState.model_validate(
                {"state_delta": "y", "closure_status": "clean"}
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestSessionState -v`

Expected: `ImportError` or `AttributeError` — `SessionState` not in `wizard.schemas`.

- [ ] **Step 3: Implement `SessionState`**

Add to `src/wizard/schemas.py` (place near top, after existing imports, before any response classes):

```python
from typing import Literal

from pydantic import BaseModel, Field


class SessionState(BaseModel):
    """Six-field structured session state written by session_end (M2)
    and read by resume_session (M3). Stored as JSON in
    wizardsession.session_state. Defined here in M1 so M2 can lift it
    verbatim without a duplicate schema."""

    intent: str
    working_set: list[int] = Field(default_factory=list)
    state_delta: str
    open_loops: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    closure_status: Literal["clean", "interrupted", "blocked"]
```

If `from typing import Literal` and `from pydantic import BaseModel, Field` are already imported, do not duplicate them — extend the existing imports instead.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py::TestSessionState -v`

Expected: 4 passed.

- [ ] **Step 5: Run full test suite to confirm no regression**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/schemas.py tests/test_models.py
git commit -m "feat: add SessionState pydantic schema for session_end persistence"
```

---

## Task 2: Add `mental_model` column to `Note` model

**Files:**
- Modify: `src/wizard/models.py` (extend `Note` class)
- Test: `tests/test_models.py` (add `class TestNoteMentalModel:` block)

**Note:** No migration yet — Task 5 generates one migration covering all three schema changes. The conftest fixture rebuilds metadata via `SQLModel.metadata.create_all`, so model-only changes are exercisable from tests without Alembic.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
from wizard.models import Note, NoteType


class TestNoteMentalModel:
    def test_note_can_store_mental_model(self, db_session):
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Auth fails due to a token-refresh race condition",
        )
        db_session.add(note)
        db_session.flush()
        db_session.refresh(note)
        assert note.mental_model == "Auth fails due to a token-refresh race condition"

    def test_mental_model_defaults_to_none(self, db_session):
        note = Note(note_type=NoteType.DOCS, content="x")
        db_session.add(note)
        db_session.flush()
        db_session.refresh(note)
        assert note.mental_model is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestNoteMentalModel -v`

Expected: `TypeError: Note.__init__() got an unexpected keyword argument 'mental_model'`.

- [ ] **Step 3: Add `mental_model` to `Note`**

In `src/wizard/models.py`, in the `Note` class, add this field (place it after `content` and before `source_id`):

```python
mental_model: str | None = Field(
    default=None,
    description=(
        "1-2 sentence causal abstraction written by the engineer; "
        "soft cap 1500 chars at the application display layer; "
        "stored as-is, not scrubbed"
    ),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py::TestNoteMentalModel -v`

Expected: 2 passed.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/models.py tests/test_models.py
git commit -m "feat: add mental_model field to Note model"
```

---

## Task 3: Add `session_state` column to `WizardSession` model

**Files:**
- Modify: `src/wizard/models.py` (extend `WizardSession`)
- Test: `tests/test_models.py` (add `class TestWizardSessionState:` block)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
from wizard.models import WizardSession
from wizard.schemas import SessionState


class TestWizardSessionState:
    def test_session_state_defaults_to_none(self, db_session):
        session = WizardSession()
        db_session.add(session)
        db_session.flush()
        db_session.refresh(session)
        assert session.session_state is None

    def test_session_state_round_trips_json(self, db_session):
        state = SessionState(
            intent="x",
            state_delta="y",
            closure_status="clean",
        )
        session = WizardSession(session_state=state.model_dump_json())
        db_session.add(session)
        db_session.flush()
        db_session.refresh(session)
        assert session.session_state is not None
        loaded = SessionState.model_validate_json(session.session_state)
        assert loaded == state
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestWizardSessionState -v`

Expected: `TypeError: WizardSession.__init__() got an unexpected keyword argument 'session_state'`.

- [ ] **Step 3: Add `session_state` to `WizardSession`**

In `src/wizard/models.py`, in `WizardSession`, add after `daily_page_id`:

```python
session_state: str | None = Field(
    default=None,
    description=(
        "JSON-serialised SessionState (see schemas.SessionState). "
        "Null until session_end (M2) populates it. "
        "Read by resume_session (M3)."
    ),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py::TestWizardSessionState -v`

Expected: 2 passed.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/models.py tests/test_models.py
git commit -m "feat: add session_state JSON column to WizardSession"
```

---

## Task 4: Add `TaskState` model

**Files:**
- Modify: `src/wizard/models.py` (add `TaskState` class)
- Test: `tests/test_models.py` (add `class TestTaskStateModel:` block)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
import datetime as _dt

from wizard.models import Task, TaskState


class TestTaskStateModel:
    def test_task_state_defaults(self, db_session):
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        state = TaskState(
            task_id=task.id,
            last_touched_at=task.created_at,
        )
        db_session.add(state)
        db_session.flush()
        db_session.refresh(state)

        assert state.task_id == task.id
        assert state.note_count == 0
        assert state.decision_count == 0
        assert state.last_note_at is None
        assert state.last_status_change_at is None
        assert state.last_touched_at == task.created_at
        assert state.stale_days == 0

    def test_task_state_table_name_is_snake_case(self):
        assert TaskState.__tablename__ == "task_state"

    def test_task_state_can_store_all_fields(self, db_session):
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()

        now = _dt.datetime.now()
        state = TaskState(
            task_id=task.id,
            note_count=4,
            decision_count=1,
            last_note_at=now,
            last_status_change_at=now,
            last_touched_at=now,
            stale_days=2,
        )
        db_session.add(state)
        db_session.flush()
        db_session.refresh(state)
        assert state.note_count == 4
        assert state.decision_count == 1
        assert state.last_note_at == now
        assert state.stale_days == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestTaskStateModel -v`

Expected: `ImportError: cannot import name 'TaskState' from 'wizard.models'`.

- [ ] **Step 3: Add `TaskState` class**

In `src/wizard/models.py`, append after `ToolCall`:

```python
class TaskState(TimestampMixin, table=True):
    """Derived signals per Task. One-to-one with Task. Updated synchronously
    by TaskStateRepository on note save, status change, and task creation.
    Never recomputed on read.

    stale_days reflects cognitive activity (notes) only — status changes
    deliberately do NOT reset it. last_status_change_at is tracked separately
    for any query that needs to distinguish administrative from cognitive
    activity.
    """

    __tablename__ = "task_state"  # pyright: ignore[reportAssignmentType, reportIncompatibleVariableOverride]

    task_id: int = Field(
        foreign_key="task.id",
        primary_key=True,
        sa_column_kwargs={"ondelete": "CASCADE"},
    )
    note_count: int = Field(default=0, nullable=False)
    decision_count: int = Field(default=0, nullable=False)
    last_note_at: datetime.datetime | None = Field(default=None)
    last_status_change_at: datetime.datetime | None = Field(default=None)
    last_touched_at: datetime.datetime = Field(nullable=False)
    stale_days: int = Field(default=0, nullable=False)
```

No `Relationship` declarations on either side — access is always through `TaskStateRepository`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py::TestTaskStateModel -v`

Expected: 3 passed.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/models.py tests/test_models.py
git commit -m "feat: add TaskState model for derived per-task signals"
```

---

## Task 5: Generate Alembic migration with backfill

**Files:**
- Create: `alembic/versions/<hash>_add_task_state_mental_model_session_state.py`

**Why now:** all three schema changes are in models. Alembic autogenerate will pick them up. We then hand-edit the generated migration to add the backfill.

- [ ] **Step 1: Generate the migration scaffold**

Run: `uv run alembic revision --autogenerate -m "add task_state mental_model session_state"`

Note the new file path printed. Open it.

- [ ] **Step 2: Verify the autogenerated `upgrade()` includes**

The autogenerate output should contain (column order may differ):

- `op.create_table('task_state', ...)` with `task_id`, `note_count`, `decision_count`, `last_note_at`, `last_status_change_at`, `last_touched_at`, `stale_days`, `created_at`, `updated_at`, FK to `task.id` with `ondelete='CASCADE'`.
- `op.add_column('note', sa.Column('mental_model', sqlmodel.sql.sqltypes.AutoString(), nullable=True))`
- `op.add_column('wizardsession', sa.Column('session_state', sqlmodel.sql.sqltypes.AutoString(), nullable=True))`

If anything is missing, regenerate; if the autogen produced extra noise (e.g. existing tables being recreated), trim those operations — autogenerate sometimes mistakes index changes. Compare against the spec table in §1.

- [ ] **Step 3: Add the backfill block to `upgrade()`**

After all `op.create_table` / `op.add_column` calls and before `# ### end Alembic commands ###`, append:

```python
    # --- Backfill task_state for existing tasks ---
    import datetime as _dt
    from sqlalchemy import text as _sa_text

    bind = op.get_bind()
    now = _dt.datetime.now()

    tasks = bind.execute(
        _sa_text("SELECT id, source_id, created_at FROM task")
    ).fetchall()

    for t in tasks:
        notes = bind.execute(
            _sa_text(
                "SELECT created_at, note_type FROM note "
                "WHERE task_id = :tid "
                "OR (source_id = :sid AND source_type = 'JIRA' AND :sid IS NOT NULL)"
            ),
            {"tid": t.id, "sid": t.source_id},
        ).fetchall()

        note_count = len(notes)
        decision_count = sum(1 for n in notes if n.note_type == "decision")
        last_note_at = max((n.created_at for n in notes), default=None)
        last_touched_at = last_note_at if last_note_at is not None else t.created_at
        stale_days = (now - last_touched_at).days

        bind.execute(
            _sa_text(
                "INSERT INTO task_state "
                "(task_id, note_count, decision_count, last_note_at, "
                " last_status_change_at, last_touched_at, stale_days, "
                " created_at, updated_at) "
                "VALUES "
                "(:task_id, :nc, :dc, :lna, NULL, :lt, :sd, :now, :now)"
            ),
            {
                "task_id": t.id,
                "nc": note_count,
                "dc": decision_count,
                "lna": last_note_at,
                "lt": last_touched_at,
                "sd": stale_days,
                "now": now,
            },
        )
```

`downgrade()` is unchanged from autogen — it drops the columns and table in reverse order.

- [ ] **Step 4: Apply the migration to a scratch DB and confirm**

Run: `uv run alembic upgrade head`

Expected: no errors, `task_state` table exists. Verify via:

`sqlite3 wizard.db ".schema task_state"`

- [ ] **Step 5: Verify downgrade**

Run:
```
uv run alembic downgrade -1
sqlite3 wizard.db ".tables" | grep task_state
```

Expected: empty output (table removed). Also verify columns dropped:
```
sqlite3 wizard.db "PRAGMA table_info(note);" | grep mental_model
sqlite3 wizard.db "PRAGMA table_info(wizardsession);" | grep session_state
```

Expected: empty output for both.

- [ ] **Step 6: Re-upgrade and commit**

Run:
```
uv run alembic upgrade head
git add alembic/versions/
git commit -m "feat: alembic migration for task_state, mental_model, session_state with backfill"
```

---

## Task 6: Migration smoke test

**Files:**
- Create: `tests/test_migration_data_layer.py`

**Purpose:** Lock in backfill correctness so future migrations don't silently break it. The autouse `db_session` fixture in `conftest.py` uses `SQLModel.metadata.create_all` and bypasses Alembic, so we need an explicit Alembic-driven test for migration behaviour.

- [ ] **Step 1: Write the test file**

Create `tests/test_migration_data_layer.py`:

```python
"""Migration smoke test for the task_state / mental_model / session_state
release. Runs alembic upgrade against a scratch SQLite file, seeds rows
at the previous head, applies this migration, and verifies backfill +
downgrade behaviour."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


# Revision IDs for the migration under test
PREVIOUS_HEAD = "15146de1d71a"  # add toolcall table
# This task's migration ID is generated at Task 5 — insert it here once known.
# Use `alembic heads` to confirm.
NEW_HEAD = None  # FILL IN: the revision ID printed by Task 5 generation


def _alembic_config(db_path: Path) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


@pytest.fixture
def scratch_db(tmp_path):
    db_path = tmp_path / "test.db"
    yield db_path


def test_upgrade_creates_task_state_table_and_new_columns(scratch_db):
    cfg = _alembic_config(scratch_db)
    command.upgrade(cfg, PREVIOUS_HEAD)

    # Seed: two tasks, one with notes (one decision, one investigation),
    # one with no notes.
    conn = sqlite3.connect(str(scratch_db))
    conn.executescript(
        "INSERT INTO task (id, name, priority, category, status, "
        "created_at, updated_at) VALUES "
        "(1, 'with-notes', 'medium', 'issue', 'todo', "
        " '2026-04-01 10:00:00', '2026-04-01 10:00:00'), "
        "(2, 'no-notes', 'low', 'issue', 'todo', "
        " '2026-04-05 10:00:00', '2026-04-05 10:00:00');"
        "INSERT INTO note (id, note_type, content, task_id, "
        "created_at, updated_at) VALUES "
        "(10, 'investigation', 'i1', 1, "
        " '2026-04-02 12:00:00', '2026-04-02 12:00:00'), "
        "(11, 'decision', 'd1', 1, "
        " '2026-04-03 12:00:00', '2026-04-03 12:00:00');"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, NEW_HEAD or "head")

    conn = sqlite3.connect(str(scratch_db))
    conn.row_factory = sqlite3.Row

    # task_state populated for both tasks
    rows = conn.execute(
        "SELECT * FROM task_state ORDER BY task_id"
    ).fetchall()
    assert len(rows) == 2

    t1 = rows[0]
    assert t1["task_id"] == 1
    assert t1["note_count"] == 2
    assert t1["decision_count"] == 1
    assert t1["last_status_change_at"] is None
    assert t1["last_note_at"] == "2026-04-03 12:00:00"

    t2 = rows[1]
    assert t2["task_id"] == 2
    assert t2["note_count"] == 0
    assert t2["decision_count"] == 0
    assert t2["last_note_at"] is None
    assert t2["last_touched_at"] == "2026-04-05 10:00:00"

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(note)").fetchall()}
    assert "mental_model" in cols

    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(wizardsession)"
    ).fetchall()}
    assert "session_state" in cols

    conn.close()


def test_downgrade_removes_table_and_columns(scratch_db):
    cfg = _alembic_config(scratch_db)
    command.upgrade(cfg, NEW_HEAD or "head")
    command.downgrade(cfg, PREVIOUS_HEAD)

    conn = sqlite3.connect(str(scratch_db))
    conn.row_factory = sqlite3.Row

    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "task_state" not in tables

    note_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(note)"
    ).fetchall()}
    assert "mental_model" not in note_cols

    sess_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(wizardsession)"
    ).fetchall()}
    assert "session_state" not in sess_cols

    conn.close()
```

- [ ] **Step 2: Fill in `NEW_HEAD`**

Replace `NEW_HEAD = None` with the actual revision ID generated in Task 5 (the leading hash in the filename `alembic/versions/<hash>_add_task_state_mental_model_session_state.py`).

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_migration_data_layer.py -v`

Expected: 2 passed.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 5: Commit**

Run:
```
git add tests/test_migration_data_layer.py
git commit -m "test: smoke test for data layer migration upgrade and downgrade with backfill"
```

---

## Task 7: `TaskStateRepository.create_for_task`

**Files:**
- Modify: `src/wizard/repositories.py` (add new class at end)
- Test: `tests/test_repositories.py` (add `class TestTaskStateRepository:`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repositories.py`:

```python
from wizard.models import TaskState
from wizard.repositories import TaskStateRepository


class TestTaskStateRepository:
    def test_create_for_task_initialises_zero_state(self, db_session):
        from wizard.models import Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()

        repo = TaskStateRepository()
        state = repo.create_for_task(db_session, task)

        assert state.task_id == task.id
        assert state.note_count == 0
        assert state.decision_count == 0
        assert state.last_note_at is None
        assert state.last_status_change_at is None
        assert state.last_touched_at == task.created_at
        assert state.stale_days >= 0

    def test_create_for_task_persists_row(self, db_session):
        from wizard.models import Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()

        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        loaded = db_session.get(TaskState, task.id)
        assert loaded is not None
        assert loaded.task_id == task.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repositories.py::TestTaskStateRepository -v`

Expected: `ImportError: cannot import name 'TaskStateRepository'`.

- [ ] **Step 3: Implement `TaskStateRepository.create_for_task`**

Append to `src/wizard/repositories.py`:

```python
import datetime as _dt

from .models import TaskState


class TaskStateRepository:
    """Pre-computes derived signals per Task. Updated synchronously by
    create_task / save_note / update_task_status tools — never lazily on read.

    stale_days is computed at write time and stored. Status changes do NOT
    reset stale_days; only cognitive activity (note saves) advances it.
    """

    def create_for_task(self, db: Session, task: Task) -> TaskState:
        """Insert a fresh TaskState row for a newly created Task.
        All counts zero; stale_days computed from task.created_at."""
        assert task.id is not None, "Task must be flushed before creating TaskState"
        now = _dt.datetime.now()
        state = TaskState(
            task_id=task.id,
            note_count=0,
            decision_count=0,
            last_note_at=None,
            last_status_change_at=None,
            last_touched_at=task.created_at,
            stale_days=(now - task.created_at).days,
        )
        db.add(state)
        db.flush()
        db.refresh(state)
        return state
```

If `import datetime as _dt` and `from .models import TaskState` are not yet present at the top of the file, add them to the existing imports.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_repositories.py::TestTaskStateRepository -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

Run:
```
git add src/wizard/repositories.py tests/test_repositories.py
git commit -m "feat: TaskStateRepository.create_for_task initialises per-task derived state"
```

---

## Task 8: `TaskStateRepository.on_note_saved`

**Files:**
- Modify: `src/wizard/repositories.py` (extend `TaskStateRepository`)
- Test: `tests/test_repositories.py` (extend `TestTaskStateRepository`)

- [ ] **Step 1: Write the failing tests**

Append to the `TestTaskStateRepository` class:

```python
    def test_on_note_saved_increments_note_count(self, db_session):
        from wizard.models import Note, NoteType, Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        note = Note(note_type=NoteType.INVESTIGATION, content="i", task_id=task.id)
        db_session.add(note)
        db_session.flush()

        state = repo.on_note_saved(db_session, task.id)
        assert state.note_count == 1
        assert state.decision_count == 0
        assert state.last_note_at == note.created_at
        assert state.last_touched_at == note.created_at

    def test_on_note_saved_counts_decisions(self, db_session):
        from wizard.models import Note, NoteType, Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        for nt, content in [
            (NoteType.INVESTIGATION, "i1"),
            (NoteType.DECISION, "d1"),
            (NoteType.DECISION, "d2"),
            (NoteType.DOCS, "doc1"),
        ]:
            db_session.add(Note(note_type=nt, content=content, task_id=task.id))
            db_session.flush()
            repo.on_note_saved(db_session, task.id)

        state = db_session.get(TaskState, task.id)
        assert state.note_count == 4
        assert state.decision_count == 2

    def test_on_note_saved_does_not_touch_last_status_change_at(self, db_session):
        import datetime as _dt
        from wizard.models import Note, NoteType, Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        sentinel = _dt.datetime(2020, 1, 1, 12, 0, 0)
        state = db_session.get(TaskState, task.id)
        state.last_status_change_at = sentinel
        db_session.add(state)
        db_session.flush()

        db_session.add(Note(note_type=NoteType.INVESTIGATION, content="x", task_id=task.id))
        db_session.flush()
        result = repo.on_note_saved(db_session, task.id)

        assert result.last_status_change_at == sentinel

    def test_on_note_saved_dual_lookup_finds_jira_anchored_notes(self, db_session):
        from wizard.models import Note, NoteType, Task
        task = Task(name="t", source_id="AUTH-123", source_type="JIRA")
        db_session.add(task)
        db_session.flush()
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        # Note attached only by source_id (not task_id) — simulates an
        # earlier note saved before the task row existed locally.
        db_session.add(Note(
            note_type=NoteType.INVESTIGATION,
            content="historical",
            source_id="AUTH-123",
            source_type="JIRA",
        ))
        db_session.flush()

        state = repo.on_note_saved(db_session, task.id)
        assert state.note_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repositories.py::TestTaskStateRepository -v`

Expected: `AttributeError: 'TaskStateRepository' object has no attribute 'on_note_saved'`.

- [ ] **Step 3: Implement `on_note_saved`**

Add inside `TaskStateRepository` (after `create_for_task`):

```python
    def on_note_saved(self, db: Session, task_id: int) -> TaskState:
        """Re-query notes for the task (dual-lookup: by task_id OR by Jira
        source_id) and recompute note_count, decision_count, last_note_at,
        last_touched_at, stale_days. Does NOT touch last_status_change_at."""
        from .models import Note  # local import to avoid circularity if any

        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        state = self._get_or_create(db, task)

        conditions = [Note.task_id == task_id]
        if task.source_id is not None:
            conditions.append(
                and_(Note.source_id == task.source_id, Note.source_type == "JIRA")
            )
        notes = db.exec(select(Note).where(or_(*conditions))).all()

        state.note_count = len(notes)
        state.decision_count = sum(
            1 for n in notes if n.note_type.value == "decision"
        )
        state.last_note_at = (
            max(n.created_at for n in notes) if notes else None
        )
        state.last_touched_at = (
            state.last_note_at if state.last_note_at is not None else task.created_at
        )
        state.stale_days = (_dt.datetime.now() - state.last_touched_at).days
        db.add(state)
        db.flush()
        db.refresh(state)
        return state
```

`and_`, `or_`, `select` are already imported at the top of `repositories.py` — verify.

- [ ] **Step 4: Add the `_get_or_create` private helper**

After `on_note_saved`, add:

```python
    def _get_or_create(self, db: Session, task: Task) -> TaskState:
        """Defensive helper: returns the TaskState for `task`, creating one
        with zero counts if missing. Used internally by on_note_saved and
        on_status_changed to handle the gap window between deploy and
        backfill, or any task created before the migration ran."""
        assert task.id is not None
        state = db.get(TaskState, task.id)
        if state is not None:
            return state
        return self.create_for_task(db, task)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_repositories.py::TestTaskStateRepository -v`

Expected: all green.

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/repositories.py tests/test_repositories.py
git commit -m "feat: TaskStateRepository.on_note_saved recomputes counts and stale_days"
```

---

## Task 9: `TaskStateRepository.on_status_changed`

**Files:**
- Modify: `src/wizard/repositories.py` (extend `TaskStateRepository`)
- Test: `tests/test_repositories.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `TestTaskStateRepository`:

```python
    def test_on_status_changed_sets_timestamp_and_preserves_other_fields(self, db_session):
        import datetime as _dt
        from wizard.models import Note, NoteType, Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        # Seed some cognitive activity.
        db_session.add(Note(note_type=NoteType.INVESTIGATION, content="i", task_id=task.id))
        db_session.add(Note(note_type=NoteType.DECISION, content="d", task_id=task.id))
        db_session.flush()
        repo.on_note_saved(db_session, task.id)

        before = db_session.get(TaskState, task.id)
        old_note_count = before.note_count
        old_decision_count = before.decision_count
        old_last_note_at = before.last_note_at
        old_last_touched_at = before.last_touched_at
        old_stale_days = before.stale_days

        result = repo.on_status_changed(db_session, task.id)

        assert result.last_status_change_at is not None
        assert (_dt.datetime.now() - result.last_status_change_at).total_seconds() < 5
        # Everything else preserved — no reset of stale_days
        assert result.note_count == old_note_count
        assert result.decision_count == old_decision_count
        assert result.last_note_at == old_last_note_at
        assert result.last_touched_at == old_last_touched_at
        assert result.stale_days == old_stale_days

    def test_on_status_changed_creates_state_if_missing(self, db_session):
        from wizard.models import Task
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()

        # Don't call create_for_task — simulate a gap-window task.
        repo = TaskStateRepository()
        result = repo.on_status_changed(db_session, task.id)
        assert result.task_id == task.id
        assert result.last_status_change_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repositories.py::TestTaskStateRepository -v`

Expected: `AttributeError: ... 'on_status_changed'`.

- [ ] **Step 3: Implement `on_status_changed`**

Add inside `TaskStateRepository`:

```python
    def on_status_changed(self, db: Session, task_id: int) -> TaskState:
        """Set last_status_change_at = now. Touches NO other field —
        status change is administrative, not cognitive. stale_days
        deliberately does not reset."""
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        state = self._get_or_create(db, task)
        state.last_status_change_at = _dt.datetime.now()
        db.add(state)
        db.flush()
        db.refresh(state)
        return state
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_repositories.py::TestTaskStateRepository -v`

Expected: all green.

- [ ] **Step 5: Commit**

Run:
```
git add src/wizard/repositories.py tests/test_repositories.py
git commit -m "feat: TaskStateRepository.on_status_changed records administrative activity"
```

---

## Task 10: `task_state_repo()` dep singleton

**Files:**
- Modify: `src/wizard/deps.py`
- Test: `tests/test_repositories.py` (one assertion)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repositories.py`:

```python
def test_task_state_repo_singleton_is_cached():
    from wizard.deps import task_state_repo
    task_state_repo.cache_clear()
    a = task_state_repo()
    b = task_state_repo()
    assert a is b
    assert isinstance(a, TaskStateRepository)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repositories.py::test_task_state_repo_singleton_is_cached -v`

Expected: `ImportError: cannot import name 'task_state_repo'`.

- [ ] **Step 3: Add the factory**

In `src/wizard/deps.py`, add at the end:

```python
@lru_cache
def task_state_repo() -> TaskStateRepository:
    logger.debug("Creating TaskStateRepository singleton")
    return TaskStateRepository()
```

And extend the import line:

```python
from .repositories import MeetingRepository, NoteRepository, TaskRepository, TaskStateRepository
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_repositories.py::test_task_state_repo_singleton_is_cached -v`

Expected: passed.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/deps.py tests/test_repositories.py
git commit -m "feat: task_state_repo dep singleton"
```

---

## Task 11: Wire `create_task` tool

**Files:**
- Modify: `src/wizard/tools.py` (`create_task` body)
- Test: `tests/test_tools.py` (add test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
def test_create_task_creates_paired_task_state(monkeypatch, db_session):
    from tests.helpers import mock_session
    from wizard.models import TaskState
    import wizard.tools as tools

    monkeypatch.setattr(tools, "get_session", mock_session(db_session))
    # If create_task does a Notion write-back, stub it as a no-op here —
    # match the existing test pattern (look for similar stubs in this file).

    response = tools.create_task(name="new task", priority="medium", category="issue")

    state = db_session.get(TaskState, response.task_id)
    assert state is not None
    assert state.note_count == 0
    assert state.decision_count == 0
```

If the existing tests in `test_tools.py` use a different stubbing pattern for Notion calls, mirror it. Inspect a passing `create_task` test first (`grep -n create_task tests/test_tools.py`) to confirm the right shape.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_create_task_creates_paired_task_state -v`

Expected: assertion failure — `state is None`.

- [ ] **Step 3: Wire the call**

In `src/wizard/tools.py` `create_task` function, after `db.add(task); db.flush()` (find via `grep -n "def create_task" src/wizard/tools.py` and read the surrounding block), insert:

```python
        from .deps import task_state_repo
        task_state_repo().create_for_task(db, task)
```

(Local import keeps the existing import block tidy and avoids re-ordering. Alternatively, add to the existing top-of-file import — your call. Match what's already used elsewhere in `tools.py` — many tools use top-level imports of `deps`.)

If `task_state_repo` is already importable via the existing `from .deps import ...` line, extend that line instead.

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_tools.py::test_create_task_creates_paired_task_state -v`

Expected: passed.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -x`

Expected: all green. (If a pre-existing `create_task` test broke because it didn't expect a `task_state` row, update it — the new behaviour is correct.)

- [ ] **Step 6: Commit**

Run:
```
git add src/wizard/tools.py tests/test_tools.py
git commit -m "feat: create_task initialises paired TaskState row"
```

---

## Task 12: Wire `save_note` tool with optional `mental_model` param

**Files:**
- Modify: `src/wizard/tools.py` (`save_note` signature + body)
- Modify: `src/wizard/schemas.py` (extend `SaveNoteResponse`)
- Test: `tests/test_tools.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
def test_save_note_stores_mental_model_when_provided(monkeypatch, db_session):
    from tests.helpers import mock_session
    from wizard.models import Note, NoteType, Task, TaskState
    import wizard.tools as tools

    monkeypatch.setattr(tools, "get_session", mock_session(db_session))

    task = Task(name="t")
    db_session.add(task)
    db_session.flush()
    state = TaskState(task_id=task.id, last_touched_at=task.created_at)
    db_session.add(state)
    db_session.flush()

    response = tools.save_note(
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="findings",
        mental_model="Race condition between token refresh and request",
    )

    note = db_session.get(Note, response.note_id)
    assert note.mental_model == "Race condition between token refresh and request"
    assert response.mental_model == note.mental_model


def test_save_note_leaves_mental_model_null_when_not_provided(monkeypatch, db_session):
    from tests.helpers import mock_session
    from wizard.models import Note, NoteType, Task, TaskState
    import wizard.tools as tools

    monkeypatch.setattr(tools, "get_session", mock_session(db_session))

    task = Task(name="t")
    db_session.add(task)
    db_session.flush()
    state = TaskState(task_id=task.id, last_touched_at=task.created_at)
    db_session.add(state)
    db_session.flush()

    response = tools.save_note(
        task_id=task.id,
        note_type=NoteType.DOCS,
        content="ref material",
    )

    note = db_session.get(Note, response.note_id)
    assert note.mental_model is None
    assert response.mental_model is None


def test_save_note_updates_task_state(monkeypatch, db_session):
    from tests.helpers import mock_session
    from wizard.models import NoteType, Task, TaskState
    import wizard.tools as tools

    monkeypatch.setattr(tools, "get_session", mock_session(db_session))

    task = Task(name="t")
    db_session.add(task)
    db_session.flush()
    state = TaskState(task_id=task.id, last_touched_at=task.created_at)
    db_session.add(state)
    db_session.flush()

    tools.save_note(task_id=task.id, note_type=NoteType.DECISION, content="d")
    db_session.refresh(state)
    assert state.note_count == 1
    assert state.decision_count == 1
    assert state.last_note_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k save_note -v`

Expected: `TypeError: save_note() got an unexpected keyword argument 'mental_model'` on test 1, assertion failures on tests 2 and 3.

- [ ] **Step 3: Update `SaveNoteResponse`**

In `src/wizard/schemas.py`, in the existing `SaveNoteResponse` class, add:

```python
mental_model: str | None = None
```

- [ ] **Step 4: Update `save_note` signature and body**

In `src/wizard/tools.py`, find the `save_note` function. Update the signature to:

```python
def save_note(
    task_id: int,
    note_type: NoteType,
    content: str,
    mental_model: str | None = None,
) -> SaveNoteResponse:
```

In the body, after the existing scrubbing of `content` and before the existing `Note(...)` construction, ensure `mental_model=mental_model` is added to the `Note(...)` kwargs.

After `note_repo().save(db, note)`, add:

```python
        from .deps import task_state_repo
        task_state_repo().on_note_saved(db, task_id)
```

(Or add `task_state_repo` to the existing top-of-file `from .deps import ...` line.)

In the response construction, add `mental_model=note.mental_model` to the `SaveNoteResponse(...)` kwargs.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_tools.py -k save_note -v`

Expected: all three pass.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 7: Commit**

Run:
```
git add src/wizard/tools.py src/wizard/schemas.py tests/test_tools.py
git commit -m "feat: save_note accepts optional mental_model and updates TaskState"
```

---

## Task 13: Wire `update_task_status` tool

**Files:**
- Modify: `src/wizard/tools.py` (`update_task_status` body)
- Modify: `src/wizard/schemas.py` (extend `UpdateTaskStatusResponse`)
- Test: `tests/test_tools.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tools.py`:

```python
def test_update_task_status_records_last_status_change_at(monkeypatch, db_session):
    import datetime as _dt
    from tests.helpers import mock_session
    from wizard.models import Task, TaskState, TaskStatus
    import wizard.tools as tools

    monkeypatch.setattr(tools, "get_session", mock_session(db_session))
    # Stub Jira and Notion write-backs as no-ops — match existing
    # update_task_status test stubbing pattern in this file.

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.flush()
    state = TaskState(task_id=task.id, last_touched_at=task.created_at)
    db_session.add(state)
    db_session.flush()

    tools.update_task_status(task_id=task.id, new_status=TaskStatus.IN_PROGRESS)

    db_session.refresh(state)
    assert state.last_status_change_at is not None
    delta = _dt.datetime.now() - state.last_status_change_at
    assert delta.total_seconds() < 5


def test_update_task_status_does_not_reset_stale_days(monkeypatch, db_session):
    from tests.helpers import mock_session
    from wizard.models import Task, TaskState, TaskStatus
    import wizard.tools as tools

    monkeypatch.setattr(tools, "get_session", mock_session(db_session))

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.flush()
    state = TaskState(
        task_id=task.id,
        last_touched_at=task.created_at,
        stale_days=7,
        note_count=3,
        decision_count=1,
    )
    db_session.add(state)
    db_session.flush()

    tools.update_task_status(task_id=task.id, new_status=TaskStatus.DONE)

    db_session.refresh(state)
    assert state.stale_days == 7
    assert state.note_count == 3
    assert state.decision_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k update_task_status -v`

Expected: `state.last_status_change_at` is None after the call.

- [ ] **Step 3: Update `UpdateTaskStatusResponse`**

In `src/wizard/schemas.py`, in the existing `UpdateTaskStatusResponse` class, add:

```python
task_state_updated: bool = True
```

- [ ] **Step 4: Wire the call in `update_task_status`**

In `src/wizard/tools.py` `update_task_status` function body, the sequence inside the `with get_session() as db:` block must be (read existing code carefully and reorder if necessary):

1. Load task.
2. Update `task.status = new_status`.
3. `db.flush()`.
4. `task_state_repo().on_status_changed(db, task.id)`.
5. Existing Jira write-back call.
6. Existing Notion write-back call.

Add the new call between steps 3 and 5. The principle is: TaskState updates **before** external write-backs.

In the response construction, add `task_state_updated=True`.

If `task_state_repo` is not yet imported, add to the existing top-of-file import.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_tools.py -k update_task_status -v`

Expected: both pass.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -x`

Expected: all green.

- [ ] **Step 7: Commit**

Run:
```
git add src/wizard/tools.py src/wizard/schemas.py tests/test_tools.py
git commit -m "feat: update_task_status records last_status_change_at without resetting stale_days"
```

---

## Task 14: End-to-end manual verification

**Files:** none modified.

**Purpose:** prove the migration applies cleanly to the user's actual `wizard.db` and that `wizard doctor` is satisfied.

- [ ] **Step 1: Backup the live DB**

Run: `cp ~/.wizard/wizard.db ~/.wizard/wizard.db.pre-data-layer.bak`

- [ ] **Step 2: Apply the migration**

Run: `uv run alembic upgrade head`

Expected: no errors. Output includes the new revision being applied.

- [ ] **Step 3: Verify schema**

Run:
```
sqlite3 ~/.wizard/wizard.db ".schema task_state"
sqlite3 ~/.wizard/wizard.db "PRAGMA table_info(note);" | grep mental_model
sqlite3 ~/.wizard/wizard.db "PRAGMA table_info(wizardsession);" | grep session_state
```

Expected: `task_state` schema printed with all eight columns; `mental_model` column shown on `note`; `session_state` column shown on `wizardsession`.

- [ ] **Step 4: Verify backfill**

Run:
```
sqlite3 ~/.wizard/wizard.db "SELECT COUNT(*) FROM task;"
sqlite3 ~/.wizard/wizard.db "SELECT COUNT(*) FROM task_state;"
```

Expected: both counts equal.

Run:
```
sqlite3 ~/.wizard/wizard.db "SELECT task_id, note_count, decision_count, last_note_at IS NULL, last_status_change_at FROM task_state LIMIT 5;"
```

Expected: rows with sane counts; `last_status_change_at` is null for all rows (no historical reconstruction); `last_note_at` is null for tasks without notes, populated otherwise.

- [ ] **Step 5: Run wizard doctor**

Run: `uv run wizard doctor`

Expected: passes (or if it warns about something unrelated to this release, note that and continue).

- [ ] **Step 6: Restore backup if any anomaly was found**

If steps 3–5 surfaced any problem, restore:

`cp ~/.wizard/wizard.db.pre-data-layer.bak ~/.wizard/wizard.db`

Otherwise, leave the migrated DB in place and remove the backup once verification is complete:

`rm ~/.wizard/wizard.db.pre-data-layer.bak`

- [ ] **Step 7: No commit needed for this task** — verification is read-only.

---

## Task 15: Push branch and open PR

**Files:** none modified.

- [ ] **Step 1: Confirm branch is clean**

Run: `git status`

Expected: nothing to commit, working tree clean.

- [ ] **Step 2: Push the branch**

Run: `git push -u origin feat/a-data-layer-foundation`

- [ ] **Step 3: Open the PR via gh CLI with HEREDOC body**

PR title: `feat: data layer foundation — TaskState, mental_model, session_state`

PR body (Markdown):

```
## Summary

Sub-project A of the v1.1.5 blueprint. Schema-only release that unblocks every downstream cognitive feature (Milestones 2 and 3) with **zero user-visible behaviour change**.

- New `task_state` table (one-to-one with `task`) with synchronous derived signals: `note_count`, `decision_count`, `last_note_at`, `last_status_change_at`, `last_touched_at`, `stale_days`.
- New `note.mental_model` column (TEXT NULLABLE, soft cap 1500 chars at the application layer, not scrubbed).
- New `wizardsession.session_state` column (TEXT NULLABLE, JSON-serialised `SessionState` Pydantic model) — null until M2 starts populating it.
- One Alembic migration with backfill from existing notes.
- `TaskStateRepository` with `create_for_task`, `on_note_saved`, `on_status_changed`, `_get_or_create`.
- Three tools wire up the repository: `create_task`, `save_note` (gains optional `mental_model` last-positional param), `update_task_status` (TaskState updated before external write-backs).
- Cascade policy: new FKs declare `ON DELETE CASCADE`; legacy bare FKs deferred to M4 sub-project H.

Spec: `docs/superpowers/specs/2026-04-13-data-layer-foundation-design.md`
Plan: `docs/superpowers/plans/2026-04-13-data-layer-foundation.md`

Auto-bump: minor (first `feat:` commit) → v1.1.4.

## Test plan

- [x] `pytest -x` green on the branch
- [x] `tests/test_migration_data_layer.py` exercises upgrade + downgrade + backfill on a scratch SQLite file
- [x] Manual `alembic upgrade head` against `~/.wizard/wizard.db` succeeds and backfills correctly
- [x] `wizard doctor` passes against the migrated DB
```

- [ ] **Step 4: Wait for CI green, then merge** (manual user step — no command).

After merge, the release workflow auto-bumps to v1.1.4 and tags `v1.1.4`. Confirm with `git fetch && git tag -l`.

---

## Self-review checklist (run after writing the plan, before handing off)

1. **Spec coverage:**
   - §1 Schema changes → Tasks 2, 3, 4, 5
   - §2 Backfill → Task 5 (step 3)
   - §3 Models → Tasks 2, 3, 4
   - §4 Schemas → Tasks 1, 12, 13
   - §5 Repositories → Tasks 7, 8, 9 (and `_get_or_create` in 8)
   - §6 Tool wiring → Tasks 11, 12, 13
   - §7 deps wiring → Task 10
   - §8 Tests → Tasks 1, 2, 3, 4, 6, 7, 8, 9, 12, 13
   - §9 Migration name → Task 5 (filename pattern matched)
   - §"Reviewer decisions" cascade policy → Task 4 (FK declaration), spec retains the M4 follow-up note

2. **Placeholder scan:** No "TBD" / "TODO" / "implement later" remain. The single `NEW_HEAD = None  # FILL IN` in Task 6 is intentional — Task 5 generates the hash, Task 6 uses it. Step 2 of Task 6 explicitly instructs the operator to fill it in.

3. **Type consistency:** `TaskStateRepository` methods used in tasks 11, 12, 13 (`create_for_task`, `on_note_saved`, `on_status_changed`) match exactly what's defined in tasks 7, 8, 9. `SaveNoteResponse.mental_model` referenced in Task 12 step 1 matches the addition in Task 12 step 3. `UpdateTaskStatusResponse.task_state_updated` referenced in Task 13 step 1 matches the addition in Task 13 step 3.

4. **Branching/release:** Branch already exists (`feat/a-data-layer-foundation` at `dd43c22`). All implementation commits land on this branch. Task 15 pushes and opens the PR. Auto-bump to v1.1.4 happens on merge.
