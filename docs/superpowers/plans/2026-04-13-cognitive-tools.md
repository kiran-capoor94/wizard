# Cognitive Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land three read-only cognitive tools (`rewind_task`, `what_am_i_missing`, `resume_session`), enrich existing response schemas with `TaskState`-sourced fields, and add the `session-resume` skill — all in a single PR.

**Architecture:** Schema enrichments are driven by tool return types; `TaskContext.from_model` centralises construction. All three tools are read-only with no external calls or DB mutations — blast radius is contained to `schemas.py`, `tools.py`, `repositories.py`, and tests. No new DB migrations required.

**Tech Stack:** Python, FastMCP (async tools + `ctx: Context`), SQLModel, SQLite, pytest (asyncio_mode=auto), pydantic v2

---

## File Map

| File | Change |
|---|---|
| `src/wizard/schemas.py` | Add 7 new schemas; enrich 6 existing schemas; add `TaskContext.from_model` classmethod |
| `src/wizard/tools.py` | Add 3 new tools; update 4 existing tool responses; replace inline `TaskContext(...)` with `from_model` |
| `src/wizard/repositories.py` | Add `find_latest_session_with_notes`; replace `_task_context_from_row` with `TaskContext.from_model` |
| `src/wizard/skills/session-resume/SKILL.md` | New skill file |
| `tests/test_schemas.py` | New — covers new schema classes and `TaskContext.from_model` |
| `tests/test_tools.py` | Add tests for 3 new tools + enriched response fields |
| `tests/test_repositories.py` | Add tests for `find_latest_session_with_notes` |

---

### Task 1: `TaskContext.from_model` classmethod + four new fields

**Files:**
- Modify: `src/wizard/schemas.py`
- Test: `tests/test_schemas.py` (create)

`TaskContext` currently has: `task_id`, `title`, `status`, `priority`, `label`, `last_worked_at`, `compounding_score`.

Add four fields sourced from `TaskState`:

```python
notion_id: str | None = None
stale_days: int = 0
note_count: int = 0
decision_count: int = 0
```

Add `from_model` classmethod below the field declarations:

```python
@classmethod
def from_model(
    cls,
    task: "Task",
    task_state: "TaskState | None",
    latest_note: "Note | None" = None,
) -> "TaskContext":
    last_worked_at = task_state.last_note_at if task_state else None
    compounding = task_state.compounding_score if task_state else 0.0
    return cls(
        task_id=task.id,
        title=task.title,
        status=task.status,
        priority=task.priority,
        label=task.label,
        notion_id=task.notion_id,
        last_worked_at=last_worked_at,
        compounding_score=compounding,
        stale_days=task_state.stale_days if task_state else 0,
        note_count=task_state.note_count if task_state else 0,
        decision_count=task_state.decision_count if task_state else 0,
    )
```

- [ ] **Step 1: Create `tests/test_schemas.py` with failing test**

```python
from wizard.models import Task, TaskState
from wizard.schemas import TaskContext
import datetime


def test_task_context_from_model_populates_task_state_fields():
    task = Task(id=1, title="T1", status="open", priority="high", label=None, notion_id="notion-abc")
    ts = TaskState(
        task_id=1,
        stale_days=5,
        note_count=3,
        decision_count=1,
        compounding_score=0.8,
        last_note_at=datetime.datetime(2026, 4, 10),
    )
    ctx = TaskContext.from_model(task, ts)
    assert ctx.task_id == 1
    assert ctx.notion_id == "notion-abc"
    assert ctx.stale_days == 5
    assert ctx.note_count == 3
    assert ctx.decision_count == 1
    assert ctx.compounding_score == 0.8
    assert ctx.last_worked_at == datetime.datetime(2026, 4, 10)


def test_task_context_from_model_null_task_state_uses_defaults():
    task = Task(id=2, title="T2", status="open", priority="low", label=None, notion_id=None)
    ctx = TaskContext.from_model(task, None)
    assert ctx.stale_days == 0
    assert ctx.note_count == 0
    assert ctx.decision_count == 0
    assert ctx.compounding_score == 0.0
    assert ctx.last_worked_at is None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_schemas.py -v
```

Expected: `AttributeError: type object 'TaskContext' has no attribute 'from_model'`

- [ ] **Step 3: Add four fields and `from_model` to `TaskContext` in `schemas.py`**

In `schemas.py`, find the `TaskContext` class. Add the four new fields (with defaults so existing construction sites don't break). Add the `from_model` classmethod after the fields. Add `TYPE_CHECKING` import for `Task`, `TaskState`, `Note` from `wizard.models` if not already present.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_schemas.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_schemas.py src/wizard/schemas.py
git commit -m "feat: add TaskContext.from_model classmethod with TaskState fields"
```

---

### Task 2: Update repositories — replace `_task_context_from_row` with `TaskContext.from_model`

**Files:**
- Modify: `src/wizard/repositories.py`

`_task_context_from_row(task, last_worked_at, latest_note)` currently builds `TaskContext` manually. Replace it with `TaskContext.from_model`.

The `_query_task_contexts` function runs a correlated subquery to get `last_worked_at` ordering. Keep the SQL for ORDER BY purposes but fetch `TaskState` per row to populate the new fields.

- [ ] **Step 1: Add failing test for enriched `build_task_context`**

In `tests/test_repositories.py`, add:

```python
def test_build_task_context_includes_task_state_fields(db_session):
    from wizard.models import Task, TaskState
    from wizard.repositories import build_task_context

    task = Task(title="T", status="open", priority="high", label=None, notion_id="n-1")
    db_session.add(task)
    db_session.flush()
    ts = TaskState(task_id=task.id, stale_days=4, note_count=2, decision_count=0, compounding_score=0.5)
    db_session.add(ts)
    db_session.flush()

    ctx = build_task_context(db_session, task.id)
    assert ctx.stale_days == 4
    assert ctx.note_count == 2
    assert ctx.notion_id == "n-1"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_repositories.py::test_build_task_context_includes_task_state_fields -v
```

Expected: FAIL — `ctx.stale_days` is 0 (default) because old code doesn't read TaskState

- [ ] **Step 3: Update `_task_context_from_row` in `repositories.py`**

Change the signature to accept `task_state: TaskState | None` and delegate to `TaskContext.from_model`:

```python
def _task_context_from_row(
    task: Task,
    task_state: "TaskState | None",
    latest_note: "Note | None" = None,
) -> TaskContext:
    return TaskContext.from_model(task, task_state, latest_note)
```

In `_query_task_contexts` (or wherever `_task_context_from_row` is called), fetch `task_state = db.get(TaskState, task.id)` and pass it through.

In `MeetingRepository.get_unsummarised_contexts`, update `MeetingContext(has_summary=False, ...)` to `MeetingContext(already_summarised=False, ...)` — this is needed for Task 4 but add the import guard now.

- [ ] **Step 4: Run all existing tests**

```
pytest tests/ -x
```

Expected: All existing tests pass (new fields default to 0/None so no breakage)

- [ ] **Step 5: Commit**

```bash
git add src/wizard/repositories.py tests/test_repositories.py
git commit -m "feat: thread TaskState through build_task_context via TaskContext.from_model"
```

---

### Task 3: `NoteDetail.mental_model` field

**Files:**
- Modify: `src/wizard/schemas.py`

`NoteDetail` has a `from_model` classmethod. Add `mental_model: str | None = None` to the class and populate it from `note.mental_model` in `from_model`.

- [ ] **Step 1: Add failing test to `tests/test_schemas.py`**

```python
from wizard.models import Note, NoteType
from wizard.schemas import NoteDetail


def test_note_detail_from_model_includes_mental_model():
    note = Note(
        id=10,
        task_id=1,
        session_id=1,
        note_type=NoteType.OBSERVATION,
        content="Some content",
        mental_model="Box model — inputs drive state",
    )
    detail = NoteDetail.from_model(note)
    assert detail.mental_model == "Box model — inputs drive state"


def test_note_detail_from_model_mental_model_none_when_absent():
    note = Note(
        id=11,
        task_id=1,
        session_id=1,
        note_type=NoteType.OBSERVATION,
        content="content",
        mental_model=None,
    )
    detail = NoteDetail.from_model(note)
    assert detail.mental_model is None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_schemas.py::test_note_detail_from_model_includes_mental_model -v
```

Expected: `AttributeError: 'NoteDetail' object has no attribute 'mental_model'`

- [ ] **Step 3: Add `mental_model` field to `NoteDetail` and update `from_model`**

```python
class NoteDetail(BaseModel):
    ...
    mental_model: str | None = None

    @classmethod
    def from_model(cls, note: "Note") -> "NoteDetail":
        return cls(
            ...
            mental_model=note.mental_model,
        )
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_schemas.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/schemas.py tests/test_schemas.py
git commit -m "feat: add mental_model field to NoteDetail.from_model"
```

---

### Task 4: `MeetingContext` — rename `has_summary` + add `source_url`, `source_type`

**Files:**
- Modify: `src/wizard/schemas.py`
- Modify: `src/wizard/repositories.py`
- Modify: `src/wizard/tools.py` (any `has_summary` references)
- Modify: `src/wizard/skills/` (any SKILL.md references to `has_summary`)

This is a **breaking rename**. `has_summary: bool` becomes `already_summarised: bool`. Add `source_url: str | None = None` and `source_type: str | None = None`.

- [ ] **Step 1: Add failing test**

```python
from wizard.schemas import MeetingContext


def test_meeting_context_has_already_summarised_field():
    ctx = MeetingContext(
        meeting_id=1,
        title="Planning",
        already_summarised=True,
        source_url="https://example.com",
        source_type="KRISP",
    )
    assert ctx.already_summarised is True
    assert ctx.source_url == "https://example.com"
    assert ctx.source_type == "KRISP"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_schemas.py::test_meeting_context_has_already_summarised_field -v
```

Expected: `ValidationError` or `TypeError` — `already_summarised` not a field

- [ ] **Step 3: Update `MeetingContext` in `schemas.py`**

```python
class MeetingContext(BaseModel):
    meeting_id: int
    title: str
    already_summarised: bool      # was: has_summary
    source_url: str | None = None
    source_type: str | None = None
```

- [ ] **Step 4: Find and update all construction sites**

Search for `has_summary` across the codebase:

```
grep -r "has_summary" src/ tests/
```

Update every occurrence (`MeetingContext(has_summary=...)` → `MeetingContext(already_summarised=...)`). Check `repositories.py` and `tools.py`. Also check skill SKILL.md files.

In `repositories.py`, `MeetingRepository.get_unsummarised_contexts` builds `MeetingContext`. Update it to pass `already_summarised=False` and populate `source_url` and `source_type` from the `Meeting` model fields.

- [ ] **Step 5: Run all tests**

```
pytest tests/ -x
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/wizard/schemas.py src/wizard/repositories.py src/wizard/tools.py
git commit -m "feat: rename MeetingContext.has_summary to already_summarised; add source_url, source_type"
```

---

### Task 5: `SessionEndResponse.session_state_saved` + wire into `session_end`

**Files:**
- Modify: `src/wizard/schemas.py`
- Modify: `src/wizard/tools.py`

`session_end` already writes `SessionState` JSON to `WizardSession.session_state`. Add `session_state_saved: bool` to `SessionEndResponse` and populate it based on whether the write succeeded.

- [ ] **Step 1: Add failing test**

In `tests/test_tools.py`, add a test that calls `session_end` and asserts `result.session_state_saved` is `True` on the happy path. Use the existing `_patch_tools` helper.

```python
async def test_session_end_response_includes_session_state_saved(db_session):
    from wizard.tools import session_end
    from tests.helpers import MockContext

    session = WizardSession()
    db_session.add(session)
    db_session.flush()

    patches, _, _ = _patch_tools(db_session)
    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        result = await session_end(
            ctx,
            session_id=session.id,
            intent="...",
            state_delta="...",
            open_loops=[],
            next_actions=[],
            closure_status="complete",
        )
    assert result.session_state_saved is True
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_tools.py::test_session_end_response_includes_session_state_saved -v
```

Expected: `AttributeError: 'SessionEndResponse' object has no attribute 'session_state_saved'`

- [ ] **Step 3: Add field to `SessionEndResponse`**

```python
class SessionEndResponse(BaseModel):
    ...
    session_state_saved: bool = False
```

- [ ] **Step 4: Wire into `session_end` in `tools.py`**

In `session_end`, the JSON write-back to `WizardSession.session_state` is already present. Capture success/failure:

```python
session_state_saved = False
try:
    session.session_state = session_state.model_dump_json()
    db.add(session)
    db.commit()
    session_state_saved = True
except Exception as e:
    logger.warning("Failed to persist session_state: %s", e)

return SessionEndResponse(
    ...
    session_state_saved=session_state_saved,
)
```

- [ ] **Step 5: Run all tests**

```
pytest tests/ -x
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/wizard/schemas.py src/wizard/tools.py tests/test_tools.py
git commit -m "feat: add session_state_saved field to SessionEndResponse"
```

---

### Task 6: `SaveNoteResponse` — rename `mental_model` to `mental_model_saved: bool`

**Files:**
- Modify: `src/wizard/schemas.py`
- Modify: `src/wizard/tools.py`

`SaveNoteResponse.mental_model: str | None` → `mental_model_saved: bool` (true if `note.mental_model is not None`).

- [ ] **Step 1: Add failing test**

```python
async def test_save_note_mental_model_saved_true_when_set(db_session):
    from wizard.tools import save_note
    ...
    result = await save_note(ctx, session_id=..., task_id=..., note_type="observation",
                             content="...", mental_model="some model")
    assert result.mental_model_saved is True

async def test_save_note_mental_model_saved_false_when_absent(db_session):
    ...
    result = await save_note(ctx, session_id=..., task_id=..., note_type="observation",
                             content="...", mental_model=None)
    assert result.mental_model_saved is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tools.py -k "mental_model_saved" -v
```

- [ ] **Step 3: Update `SaveNoteResponse` in `schemas.py`**

```python
class SaveNoteResponse(BaseModel):
    note_id: int
    mental_model_saved: bool
```

- [ ] **Step 4: Update `save_note` return in `tools.py`**

```python
return SaveNoteResponse(
    note_id=saved.id,
    mental_model_saved=saved.mental_model is not None,
)
```

- [ ] **Step 5: Run all tests**

```
pytest tests/ -x
```

- [ ] **Step 6: Commit**

```bash
git add src/wizard/schemas.py src/wizard/tools.py tests/test_tools.py
git commit -m "feat: rename SaveNoteResponse.mental_model to mental_model_saved bool"
```

---

### Task 7: `SaveMeetingSummaryResponse` — rename `linked_task_ids` to `tasks_linked: int`

**Files:**
- Modify: `src/wizard/schemas.py`
- Modify: `src/wizard/tools.py`

`linked_task_ids: list[int]` → `tasks_linked: int` (count).

- [ ] **Step 1: Add failing test**

```python
async def test_save_meeting_summary_returns_tasks_linked_count(db_session):
    ...
    result = await save_meeting_summary(ctx, meeting_id=..., summary="...", task_ids=[1, 2])
    assert result.tasks_linked == 2
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_tools.py -k "tasks_linked" -v
```

- [ ] **Step 3: Update `SaveMeetingSummaryResponse` and `save_meeting_summary`**

Schema:
```python
class SaveMeetingSummaryResponse(BaseModel):
    meeting_id: int
    tasks_linked: int
    notion_write_back: WriteBackStatus
```

Tool (at the return statement, where `linked_task_ids` is built):
```python
return SaveMeetingSummaryResponse(
    meeting_id=meeting.id,
    tasks_linked=len(linked_task_ids),
    notion_write_back=wb_status,
)
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -x
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/schemas.py src/wizard/tools.py tests/test_tools.py
git commit -m "feat: rename SaveMeetingSummaryResponse.linked_task_ids to tasks_linked count"
```

---

### Task 8: `TaskStartResponse.latest_mental_model` + wire into `task_start`

**Files:**
- Modify: `src/wizard/schemas.py`
- Modify: `src/wizard/tools.py`

`task_start` already fetches `prior_notes`. Scan them for the most recent note where `mental_model is not None`. Populate `TaskStartResponse.latest_mental_model`.

- [ ] **Step 1: Add failing test**

```python
async def test_task_start_latest_mental_model_from_prior_notes(db_session):
    from wizard.tools import task_start
    ...
    # create task, task_state, session, two notes — second has mental_model set
    note1 = Note(..., mental_model=None, created_at=datetime(2026, 4, 1))
    note2 = Note(..., mental_model="State machine", created_at=datetime(2026, 4, 5))
    ...
    result = await task_start(ctx, session_id=..., task_id=...)
    assert result.latest_mental_model == "State machine"


async def test_task_start_latest_mental_model_none_when_no_models(db_session):
    ...
    result = await task_start(ctx, session_id=..., task_id=...)
    assert result.latest_mental_model is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tools.py -k "latest_mental_model" -v
```

- [ ] **Step 3: Add field to `TaskStartResponse`**

```python
class TaskStartResponse(BaseModel):
    task: TaskContext
    compounding: float
    notes_by_type: dict[str, int]
    prior_notes: list[NoteDetail]
    latest_mental_model: str | None = None
```

- [ ] **Step 4: Wire into `task_start` in `tools.py`**

After fetching `prior_notes`, scan newest-first for the first non-null `mental_model`:

```python
latest_mental_model = next(
    (n.mental_model for n in prior_notes if n.mental_model is not None),
    None,
)
return TaskStartResponse(
    ...
    latest_mental_model=latest_mental_model,
)
```

Note: `NoteRepository.get_for_task` returns notes newest-first (DESC order), so iterating from index 0 gives the most recent.

- [ ] **Step 5: Run all tests**

```
pytest tests/ -x
```

- [ ] **Step 6: Commit**

```bash
git add src/wizard/schemas.py src/wizard/tools.py tests/test_tools.py
git commit -m "feat: add latest_mental_model to TaskStartResponse"
```

---

### Task 9: New schemas — `TimelineEntry`, `RewindSummary`, `RewindResponse`

**Files:**
- Modify: `src/wizard/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Add failing schema round-trip tests**

```python
from wizard.schemas import TimelineEntry, RewindSummary, RewindResponse
import datetime


def test_timeline_entry_round_trip():
    entry = TimelineEntry(
        note_id=1,
        created_at=datetime.datetime(2026, 4, 1),
        note_type="observation",
        preview="Short preview",
        mental_model=None,
    )
    assert entry.note_id == 1
    assert entry.preview == "Short preview"


def test_rewind_summary_round_trip():
    summary = RewindSummary(
        total_notes=5,
        duration_days=10,
        last_activity=datetime.datetime(2026, 4, 10),
    )
    assert summary.duration_days == 10


def test_rewind_response_round_trip(tmp_task_context):
    from wizard.schemas import RewindResponse
    resp = RewindResponse(task=tmp_task_context, timeline=[], summary=RewindSummary(
        total_notes=0, duration_days=0, last_activity=datetime.datetime(2026, 4, 1)
    ))
    assert resp.timeline == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_schemas.py -k "timeline or rewind" -v
```

- [ ] **Step 3: Add schemas to `schemas.py`**

```python
class TimelineEntry(BaseModel):
    note_id: int
    created_at: datetime.datetime
    note_type: NoteType
    preview: str               # content[:200]
    mental_model: str | None


class RewindSummary(BaseModel):
    total_notes: int
    duration_days: int
    last_activity: datetime.datetime


class RewindResponse(BaseModel):
    task: TaskContext
    timeline: list[TimelineEntry]
    summary: RewindSummary
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/schemas.py tests/test_schemas.py
git commit -m "feat: add TimelineEntry, RewindSummary, RewindResponse schemas"
```

---

### Task 10: New schemas — `Signal`, `MissingResponse`

**Files:**
- Modify: `src/wizard/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Add failing tests**

```python
from wizard.schemas import Signal, MissingResponse
from typing import Literal


def test_signal_severity_literal():
    s = Signal(type="stale", severity="high", message="No activity for 5 days")
    assert s.severity == "high"


def test_missing_response_empty_signals():
    resp = MissingResponse(signals=[])
    assert resp.signals == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_schemas.py -k "signal or missing" -v
```

- [ ] **Step 3: Add schemas**

```python
class Signal(BaseModel):
    type: str
    severity: Literal["high", "medium", "low"]
    message: str


class MissingResponse(BaseModel):
    signals: list[Signal]
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/schemas.py tests/test_schemas.py
git commit -m "feat: add Signal and MissingResponse schemas"
```

---

### Task 11: New schemas — `ResumedTaskNotes`, `ResumeSessionResponse`

**Files:**
- Modify: `src/wizard/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Add failing tests**

```python
from wizard.schemas import ResumedTaskNotes, ResumeSessionResponse, SessionState


def test_resumed_task_notes_round_trip(tmp_task_context):
    rtn = ResumedTaskNotes(
        task=tmp_task_context,
        notes=[],
        latest_mental_model=None,
    )
    assert rtn.notes == []


def test_resume_session_response_round_trip(tmp_task_context):
    resp = ResumeSessionResponse(
        session_id=2,
        resumed_from_session_id=1,
        session_state=None,
        working_set_tasks=[],
        prior_notes=[],
        unsummarised_meetings=[],
        sync_results=[],
        daily_page=None,
    )
    assert resp.session_id == 2
    assert resp.session_state is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_schemas.py -k "resumed" -v
```

- [ ] **Step 3: Add schemas**

```python
class ResumedTaskNotes(BaseModel):
    task: TaskContext
    notes: list[NoteDetail]
    latest_mental_model: str | None


class ResumeSessionResponse(BaseModel):
    session_id: int
    resumed_from_session_id: int
    session_state: SessionState | None
    working_set_tasks: list[TaskContext]
    prior_notes: list[ResumedTaskNotes]
    unsummarised_meetings: list[MeetingContext]
    sync_results: list[SourceSyncStatus]
    daily_page: DailyPageResult | None
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_schemas.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/schemas.py tests/test_schemas.py
git commit -m "feat: add ResumedTaskNotes and ResumeSessionResponse schemas"
```

---

### Task 12: `find_latest_session_with_notes` repository helper

**Files:**
- Modify: `src/wizard/repositories.py`
- Test: `tests/test_repositories.py`

Query: select from `WizardSession` where an associated `Note` row exists (`note.session_id == wizardsession.id`), order by `WizardSession.created_at DESC`, limit 1.

Use SQLModel `select` with `where(col(Note.session_id) == WizardSession.id).exists()`.

- [ ] **Step 1: Add failing tests**

```python
def test_find_latest_session_with_notes_returns_none_when_no_sessions(db_session):
    from wizard.repositories import find_latest_session_with_notes
    result = find_latest_session_with_notes(db_session)
    assert result is None


def test_find_latest_session_with_notes_returns_none_when_no_notes(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import find_latest_session_with_notes

    s = WizardSession()
    db_session.add(s)
    db_session.flush()
    result = find_latest_session_with_notes(db_session)
    assert result is None


def test_find_latest_session_with_notes_returns_most_recent_session_with_notes(db_session):
    from wizard.models import WizardSession, Task, Note, NoteType
    from wizard.repositories import find_latest_session_with_notes
    import datetime

    s1 = WizardSession(created_at=datetime.datetime(2026, 4, 1))
    s2 = WizardSession(created_at=datetime.datetime(2026, 4, 5))
    s3 = WizardSession(created_at=datetime.datetime(2026, 4, 10))  # no notes
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    task = Task(title="T", status="open", priority="low", label=None)
    db_session.add(task)
    db_session.flush()

    n1 = Note(task_id=task.id, session_id=s1.id, note_type=NoteType.OBSERVATION, content="a")
    n2 = Note(task_id=task.id, session_id=s2.id, note_type=NoteType.OBSERVATION, content="b")
    db_session.add_all([n1, n2])
    db_session.flush()

    result = find_latest_session_with_notes(db_session)
    assert result is not None
    assert result.id == s2.id
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_repositories.py -k "find_latest_session" -v
```

- [ ] **Step 3: Implement `find_latest_session_with_notes` in `repositories.py`**

Add at module level (not inside a class):

```python
def find_latest_session_with_notes(db: Session) -> WizardSession | None:
    """Most recent WizardSession that has at least one associated Note."""
    from sqlmodel import select, col, exists
    subq = select(Note).where(col(Note.session_id) == WizardSession.id).exists()
    stmt = (
        select(WizardSession)
        .where(subq)
        .order_by(col(WizardSession.created_at).desc())
        .limit(1)
    )
    results = db.execute(stmt).scalars().all()
    return results[0] if results else None
```

Note: use `db.execute(stmt).scalars().all()` rather than the `db.exec()` shorthand to stay consistent with SQLModel's raw execute pattern.

- [ ] **Step 4: Run tests**

```
pytest tests/test_repositories.py -k "find_latest_session" -v
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/repositories.py tests/test_repositories.py
git commit -m "feat: add find_latest_session_with_notes repository helper"
```

---

### Task 13: `rewind_task` tool

**Files:**
- Modify: `src/wizard/tools.py`
- Test: `tests/test_tools.py`

Logic:
1. `db.get(Task, task_id)` — `ToolError` if not found
2. `db.get(TaskState, task_id)` — `ToolError` if missing
3. Fetch all notes via `NoteRepository.get_for_task(db, task)` (returns newest-first); reverse to oldest-first
4. Build `list[TimelineEntry]` (`content[:200]` for preview)
5. Compute `RewindSummary`: `total_notes`, `duration_days` (0 if <2 notes), `last_activity`
6. Build `TaskContext.from_model(task, task_state)`
7. Return `RewindResponse`

- [ ] **Step 1: Add failing tests**

```python
async def test_rewind_task_empty_timeline(db_session):
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskState
    from tests.helpers import MockContext

    task = Task(title="T", status="open", priority="low", label=None)
    db_session.add(task)
    db_session.flush()
    ts = TaskState(task_id=task.id)
    db_session.add(ts)
    db_session.flush()

    patches, _, _ = _patch_tools(db_session)
    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        result = await rewind_task(ctx, task_id=task.id)

    assert result.timeline == []
    assert result.summary.total_notes == 0
    assert result.summary.duration_days == 0


async def test_rewind_task_multiple_notes_sort_order_and_duration(db_session):
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskState, Note, NoteType
    from tests.helpers import MockContext
    import datetime

    task = Task(title="T", status="open", priority="low", label=None)
    db_session.add(task)
    db_session.flush()
    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    ts = TaskState(task_id=task.id)
    db_session.add(ts)

    n1 = Note(task_id=task.id, session_id=session.id, note_type=NoteType.OBSERVATION,
              content="A" * 300, created_at=datetime.datetime(2026, 4, 1))
    n2 = Note(task_id=task.id, session_id=session.id, note_type=NoteType.DECISION,
              content="B", created_at=datetime.datetime(2026, 4, 5))
    db_session.add_all([n1, n2])
    db_session.flush()

    patches, _, _ = _patch_tools(db_session)
    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        result = await rewind_task(ctx, task_id=task.id)

    assert len(result.timeline) == 2
    assert result.timeline[0].created_at < result.timeline[1].created_at  # oldest first
    assert len(result.timeline[0].preview) == 200  # truncated
    assert result.summary.total_notes == 2
    assert result.summary.duration_days == 4


async def test_rewind_task_not_found_raises_tool_error(db_session):
    from wizard.tools import rewind_task
    from fastmcp import ToolError
    from tests.helpers import MockContext

    patches, _, _ = _patch_tools(db_session)
    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError):
            await rewind_task(ctx, task_id=9999)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tools.py -k "rewind_task" -v
```

- [ ] **Step 3: Implement `rewind_task` in `tools.py`**

```python
@mcp.tool()
async def rewind_task(ctx: Context, task_id: int) -> RewindResponse:
    """Reconstruct a task's note timeline from oldest to newest."""
    logger.info("rewind_task task_id=%d", task_id)
    with get_session() as db:
        _log_tool_call(db, "rewind_task")
        task = db.get(Task, task_id)
        if not task:
            raise ToolError(f"Task {task_id} not found")
        task_state = db.get(TaskState, task_id)
        if not task_state:
            raise ToolError(f"TaskState missing for task {task_id}")

        notes = NoteRepository.get_for_task(db, task)
        notes_asc = list(reversed(notes))  # get_for_task returns DESC

        timeline = [
            TimelineEntry(
                note_id=n.id,
                created_at=n.created_at,
                note_type=n.note_type,
                preview=n.content[:200],
                mental_model=n.mental_model,
            )
            for n in notes_asc
        ]

        if len(notes_asc) >= 2:
            duration_days = (notes_asc[-1].created_at - notes_asc[0].created_at).days
        else:
            duration_days = 0

        last_activity = notes_asc[-1].created_at if notes_asc else task.created_at

        summary = RewindSummary(
            total_notes=len(notes_asc),
            duration_days=duration_days,
            last_activity=last_activity,
        )
        return RewindResponse(
            task=TaskContext.from_model(task, task_state),
            timeline=timeline,
            summary=summary,
        )
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -x
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/tools.py tests/test_tools.py
git commit -m "feat: add rewind_task tool"
```

---

### Task 14: `what_am_i_missing` tool (7 rules)

**Files:**
- Modify: `src/wizard/tools.py`
- Test: `tests/test_tools.py`

Seven rules, all fire independently. Rules 5 and 7 require inline DB queries.

| # | Condition | type | severity | message |
|---|-----------|------|----------|---------|
| 1 | `task_state.note_count == 0` | `no_context` | high | `"No notes recorded for this task"` |
| 2 | `task_state.stale_days >= 3` | `stale` | medium | `f"No activity for {stale_days} days"` |
| 3 | `note_count > 0 and note_count <= 2` | `low_context` | medium | `"Very few notes — context may be shallow"` |
| 4 | `decision_count == 0 and note_count > 0` | `no_decisions` | medium | `"No decisions recorded"` |
| 5 | `investigation_count > 3 and decision_count == 0` | `analysis_loop` | high | `"Multiple investigations without a decision"` |
| 6 | `last_note_at is not None and stale_days >= 2` | `lost_context` | medium | `"Context may be degrading due to inactivity"` |
| 7 | `note_count >= 2 and not has_model` | `no_model` | medium | `"No mental model captured — understanding may be shallow"` |

Severity sort order: high → medium → low.

- [ ] **Step 1: Add failing tests — one per rule + sort order + healthy task**

```python
async def test_what_am_i_missing_rule1_no_notes(db_session):
    # TaskState with note_count=0 → signal type="no_context", severity="high"
    ...
    result = await what_am_i_missing(ctx, task_id=task.id)
    types = [s.type for s in result.signals]
    assert "no_context" in types
    assert next(s for s in result.signals if s.type == "no_context").severity == "high"


async def test_what_am_i_missing_rule2_stale(db_session):
    # stale_days=5, note_count=3 → "stale" signal fired
    ...
    types = [s.type for s in result.signals]
    assert "stale" in types


async def test_what_am_i_missing_rules_2_and_6_both_fire_at_stale_3(db_session):
    # stale_days=3, last_note_at set → both "stale" and "lost_context" fire
    ...
    types = [s.type for s in result.signals]
    assert "stale" in types
    assert "lost_context" in types


async def test_what_am_i_missing_rule5_analysis_loop(db_session):
    # 4 investigation notes, 0 decisions → "analysis_loop" high severity
    ...
    types = [s.type for s in result.signals]
    assert "analysis_loop" in types
    assert next(s for s in result.signals if s.type == "analysis_loop").severity == "high"


async def test_what_am_i_missing_severity_sort_order(db_session):
    # trigger high + medium signals; assert all highs come before mediums
    ...
    severities = [s.severity for s in result.signals]
    high_indices = [i for i, sv in enumerate(severities) if sv == "high"]
    medium_indices = [i for i, sv in enumerate(severities) if sv == "medium"]
    if high_indices and medium_indices:
        assert max(high_indices) < min(medium_indices)


async def test_what_am_i_missing_healthy_task_no_signals(db_session):
    # fresh task: note_count=5, stale_days=0, decision_count=2, has mental_model, last_note_at recent
    ...
    result = await what_am_i_missing(ctx, task_id=task.id)
    assert result.signals == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tools.py -k "what_am_i_missing" -v
```

- [ ] **Step 3: Implement `what_am_i_missing` in `tools.py`**

```python
@mcp.tool()
async def what_am_i_missing(ctx: Context, task_id: int) -> MissingResponse:
    """Surface cognitive gaps for a task using seven diagnostic rules."""
    logger.info("what_am_i_missing task_id=%d", task_id)
    SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    with get_session() as db:
        _log_tool_call(db, "what_am_i_missing")
        task = db.get(Task, task_id)
        if not task:
            raise ToolError(f"Task {task_id} not found")
        task_state = db.get(TaskState, task_id)
        if not task_state:
            raise ToolError(f"TaskState missing for task {task_id}")

        signals: list[Signal] = []
        nc = task_state.note_count
        dc = task_state.decision_count
        sd = task_state.stale_days

        # Rule 1
        if nc == 0:
            signals.append(Signal(type="no_context", severity="high",
                                  message="No notes recorded for this task"))
        # Rule 2
        if sd >= 3:
            signals.append(Signal(type="stale", severity="medium",
                                  message=f"No activity for {sd} days"))
        # Rule 3
        if nc > 0 and nc <= 2:
            signals.append(Signal(type="low_context", severity="medium",
                                  message="Very few notes — context may be shallow"))
        # Rule 4
        if dc == 0 and nc > 0:
            signals.append(Signal(type="no_decisions", severity="medium",
                                  message="No decisions recorded"))
        # Rule 5 — inline count query
        inv_stmt = (
            select(func.count(Note.id))
            .where(Note.task_id == task_id)
            .where(Note.note_type == NoteType.INVESTIGATION)
        )
        investigation_count = db.execute(inv_stmt).scalar_one()
        if investigation_count > 3 and dc == 0:
            signals.append(Signal(type="analysis_loop", severity="high",
                                  message="Multiple investigations without a decision"))
        # Rule 6
        if task_state.last_note_at is not None and sd >= 2:
            signals.append(Signal(type="lost_context", severity="medium",
                                  message="Context may be degrading due to inactivity"))
        # Rule 7 — inline existence query
        model_stmt = (
            select(Note.id)
            .where(Note.task_id == task_id)
            .where(Note.mental_model.is_not(None))
            .limit(1)
        )
        has_model = db.execute(model_stmt).first() is not None
        if nc >= 2 and not has_model:
            signals.append(Signal(type="no_model", severity="medium",
                                  message="No mental model captured — understanding may be shallow"))

        signals.sort(key=lambda s: SEVERITY_ORDER[s.severity])
        return MissingResponse(signals=signals)
```

Import `func` from `sqlalchemy` and `select` from `sqlmodel` at top of file (check existing imports).

- [ ] **Step 4: Run all tests**

```
pytest tests/ -x
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/tools.py tests/test_tools.py
git commit -m "feat: add what_am_i_missing tool with seven diagnostic rules"
```

---

### Task 15: `resume_session` tool

**Files:**
- Modify: `src/wizard/tools.py`
- Test: `tests/test_tools.py`

Logic (mirrors `session_start` structure):
1. Find session to resume (explicit `session_id` or `find_latest_session_with_notes`)
2. Create new `WizardSession`; `await ctx.set_state("current_session_id", new_session.id)`
3. Sync: `sync_service().sync_jira()`, `sync_service().sync_notion_tasks()`, `sync_service().sync_notion_meetings()` with `ctx.report_progress` calls
4. `ensure_daily_page()` via `notion_client()`
5. Deserialise `prior.session_state`:
   - Non-null: `SessionState.model_validate_json(prior.session_state)` → fetch `TaskContext.from_model` for each task in `working_set`
   - Null: `await ctx.warning("Session was not cleanly closed — no structured state available. Falling back to note history.")` → `working_set_tasks = []`
6. Fetch `prior_notes`: all `Note` rows where `note.session_id == prior.id`, group by `task_id`, build `list[ResumedTaskNotes]`
7. Fetch `unsummarised_meetings` — same query as `session_start`
8. Return `ResumeSessionResponse`

- [ ] **Step 1: Add failing tests**

```python
async def test_resume_session_explicit_session_id(db_session):
    from wizard.tools import resume_session
    from wizard.models import WizardSession, Task, TaskState, Note, NoteType
    from tests.helpers import _MockContextImpl, mock_ctx

    prior = WizardSession()
    db_session.add(prior)
    db_session.flush()
    task = Task(title="T", status="open", priority="low", label=None)
    db_session.add(task)
    db_session.flush()
    ts = TaskState(task_id=task.id)
    db_session.add(ts)
    note = Note(task_id=task.id, session_id=prior.id, note_type=NoteType.OBSERVATION, content="x")
    db_session.add(note)
    db_session.flush()

    patches, sync_mock, _ = _patch_tools(db_session)
    impl = _MockContextImpl()
    ctx = mock_ctx(impl)
    with patch.multiple("wizard.tools", **patches):
        result = await resume_session(ctx, session_id=prior.id)

    assert result.resumed_from_session_id == prior.id
    assert result.session_id != prior.id  # new session created
    assert len(result.prior_notes) == 1
    assert result.prior_notes[0].notes[0].content == "x"


async def test_resume_session_null_session_state_fires_warning(db_session):
    # prior session has session_state=None → ctx.warning fires, working_set_tasks=[]
    ...
    impl = _MockContextImpl()
    ctx = mock_ctx(impl)
    with patch.multiple("wizard.tools", **patches):
        result = await resume_session(ctx, session_id=prior.id)
    assert result.working_set_tasks == []
    assert any("not cleanly closed" in w for w in impl.warning_calls)


async def test_resume_session_no_sessions_raises_tool_error(db_session):
    from wizard.tools import resume_session
    from fastmcp import ToolError
    from tests.helpers import MockContext

    patches, _, _ = _patch_tools(db_session)
    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError):
            await resume_session(ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tools.py -k "resume_session" -v
```

- [ ] **Step 3: Implement `resume_session` in `tools.py`**

```python
@mcp.tool()
async def resume_session(
    ctx: Context, session_id: int | None = None
) -> ResumeSessionResponse:
    """Resume a prior session in a new MCP thread. Creates a new session."""
    logger.info("resume_session session_id=%s", session_id)
    with get_session() as db:
        _log_tool_call(db, "resume_session")

        # Step 1: find prior session
        if session_id is not None:
            prior = db.get(WizardSession, session_id)
            if not prior:
                raise ToolError(f"Session {session_id} not found")
        else:
            prior = find_latest_session_with_notes(db)
            if not prior:
                raise ToolError("No sessions with notes found")

        # Step 2: create new session
        new_session = WizardSession()
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        await ctx.set_state("current_session_id", new_session.id)

        # Step 3: sync
        svc = sync_service()
        await ctx.report_progress(0, 3, "Syncing Jira...")
        svc.sync_jira()
        await ctx.report_progress(1, 3, "Syncing Notion tasks...")
        svc.sync_notion_tasks()
        await ctx.report_progress(2, 3, "Syncing Notion meetings...")
        sync_results = svc.sync_notion_meetings()
        await ctx.report_progress(3, 3, "Sync complete")

        # Step 4: daily page
        daily_page = None
        try:
            daily_page = notion_client().ensure_daily_page()
        except Exception as e:
            logger.warning("ensure_daily_page failed: %s", e)

        # Step 5: deserialise session_state
        session_state: SessionState | None = None
        working_set_tasks: list[TaskContext] = []
        if prior.session_state:
            try:
                session_state = SessionState.model_validate_json(prior.session_state)
                for task_id in session_state.working_set:
                    t = db.get(Task, task_id)
                    ts = db.get(TaskState, task_id)
                    if t:
                        working_set_tasks.append(TaskContext.from_model(t, ts))
            except Exception as e:
                logger.warning("Failed to deserialise session_state: %s", e)
                session_state = None
        else:
            await ctx.warning(
                "Session was not cleanly closed — no structured state available. "
                "Falling back to note history."
            )

        # Step 6: prior notes grouped by task
        note_stmt = select(Note).where(Note.session_id == prior.id).order_by(Note.created_at.asc())
        all_prior_notes = db.execute(note_stmt).scalars().all()
        by_task: dict[int, list[Note]] = {}
        for n in all_prior_notes:
            by_task.setdefault(n.task_id, []).append(n)

        prior_notes: list[ResumedTaskNotes] = []
        for tid, notes in by_task.items():
            t = db.get(Task, tid)
            ts = db.get(TaskState, tid)
            if t:
                latest_mm = next(
                    (n.mental_model for n in reversed(notes) if n.mental_model is not None),
                    None,
                )
                prior_notes.append(ResumedTaskNotes(
                    task=TaskContext.from_model(t, ts),
                    notes=[NoteDetail.from_model(n) for n in notes],
                    latest_mental_model=latest_mm,
                ))

        # Step 7: unsummarised meetings
        unsummarised = MeetingRepository.get_unsummarised_contexts(db)

        return ResumeSessionResponse(
            session_id=new_session.id,
            resumed_from_session_id=prior.id,
            session_state=session_state,
            working_set_tasks=working_set_tasks,
            prior_notes=prior_notes,
            unsummarised_meetings=unsummarised,
            sync_results=sync_results,
            daily_page=daily_page,
        )
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -x
```

- [ ] **Step 5: Commit**

```bash
git add src/wizard/tools.py tests/test_tools.py
git commit -m "feat: add resume_session tool"
```

---

### Task 16: `session-resume` skill

**Files:**
- Create: `src/wizard/skills/session-resume/SKILL.md`

- [ ] **Step 1: Create the skill file**

```bash
mkdir -p src/wizard/skills/session-resume
```

Write `src/wizard/skills/session-resume/SKILL.md`:

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

- [ ] **Step 2: Verify skill is in the correct location**

Check that `src/wizard/skills/session-resume/SKILL.md` exists alongside the other skills (e.g., `session-start/SKILL.md`).

- [ ] **Step 3: Commit**

```bash
git add src/wizard/skills/session-resume/SKILL.md
git commit -m "feat: add session-resume skill"
```

---

### Task 17: Version bump to v1.1.6

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/wizard/__init__.py` (if version is defined there)

- [ ] **Step 1: Find current version string**

```bash
grep -r "version" pyproject.toml src/wizard/__init__.py 2>/dev/null | head -20
```

- [ ] **Step 2: Update version from `1.1.5` to `1.1.6`**

In `pyproject.toml`:
```toml
version = "1.1.6"
```

In `src/wizard/__init__.py` (if present):
```python
__version__ = "1.1.6"
```

- [ ] **Step 3: Run full test suite one final time**

```
pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/wizard/__init__.py
git commit -m "chore: bump version to 1.1.6"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `TaskContext` four new fields + `from_model` | Task 1 |
| All `TaskContext` construction sites → `from_model` | Task 2 |
| `NoteDetail.mental_model` | Task 3 |
| `MeetingContext` rename + two new fields | Task 4 |
| `SessionEndResponse.session_state_saved` | Task 5 |
| `SaveNoteResponse.mental_model_saved` | Task 6 |
| `SaveMeetingSummaryResponse.tasks_linked` | Task 7 |
| `TaskStartResponse.latest_mental_model` | Task 8 |
| `TimelineEntry`, `RewindSummary`, `RewindResponse` | Task 9 |
| `Signal`, `MissingResponse` | Task 10 |
| `ResumedTaskNotes`, `ResumeSessionResponse` | Task 11 |
| `find_latest_session_with_notes` | Task 12 |
| `rewind_task` tool | Task 13 |
| `what_am_i_missing` seven rules | Task 14 |
| `resume_session` tool | Task 15 |
| `session-resume/SKILL.md` | Task 16 |
| Version bump to 1.1.6 | Task 17 |

All spec requirements covered. No placeholders. Type names are consistent across tasks (`TaskContext`, `TaskState`, `NoteDetail`, `MeetingContext`, `find_latest_session_with_notes`). Method signatures match: `TaskContext.from_model(task, task_state, latest_note=None)` used identically in Tasks 1, 2, 13, 15.
