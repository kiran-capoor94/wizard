# Bug Audit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 11 confirmed bugs across four severity tiers, TDD throughout, one commit per tier.

**Architecture:** Severity-gated — critical data-integrity bugs first, then wrong-output analytics bugs, then medium inconsistencies, then low design gaps. Each tier is self-contained and committed before the next begins.

**Tech Stack:** Python 3.14, SQLModel, FastMCP, pytest, respx

---

## File Map

| File | Changes |
|------|---------|
| `src/wizard/integrations.py` | Add `_is_daily_page_title`, fix `ensure_daily_page` stale filter |
| `src/wizard/tools.py` | Remove explicit `db.commit()` in `update_task`; reverse note order in `task_start`; update docstrings; replace `assert` with `ToolError`; fix `what_am_i_missing` rule 6 |
| `src/wizard/cli/analytics.py` | Fix `query_compounding` boundary; fix `query_tasks` None key |
| `src/wizard/cli/main.py` | Fix `_check_notion_schema` hardcoded meeting category |
| `src/wizard/models.py` | Fix `Note.mental_model` docstring; fix `ToolCall.called_at` timezone |
| `tests/test_integrations.py` | Tests for Fix 1 |
| `tests/test_tools.py` | Tests for Fix 2, 7, 10, 11 |
| `tests/test_cli_analytics.py` | Tests for Fix 3, 4 |
| `tests/test_cli.py` | Tests for Fix 5 |
| `tests/test_models.py` | Tests for Fix 8 |

---

## Task 1 — Fix 1a: `_is_daily_page_title` helper (Tier 1)

**Files:**
- Modify: `src/wizard/integrations.py` (add helper before `NotionClient` class)
- Modify: `tests/test_integrations.py` (new test class)

- [ ] **Step 1: Write the failing tests**

Add at the end of `tests/test_integrations.py`, before the `NotionClient` section:

```python
class TestIsDailyPageTitle:
    def test_returns_true_for_valid_daily_title(self):
        from wizard.integrations import _is_daily_page_title
        assert _is_daily_page_title("Wednesday 9 April 2025") is True
        assert _is_daily_page_title("Monday 1 January 2024") is True
        assert _is_daily_page_title("Friday 15 April 2026") is True

    def test_returns_false_for_non_daily_titles(self):
        from wizard.integrations import _is_daily_page_title
        assert _is_daily_page_title("SISU IQ Design") is False
        assert _is_daily_page_title("") is False
        assert _is_daily_page_title("2024-01-01") is False
        assert _is_daily_page_title("Meeting Notes") is False
        assert _is_daily_page_title("9 April 2025") is False  # missing weekday
```

- [ ] **Step 2: Run to confirm failure**

```
.venv/bin/python -m pytest tests/test_integrations.py::TestIsDailyPageTitle -xvs
```

Expected: `ImportError: cannot import name '_is_daily_page_title'`

- [ ] **Step 3: Add `_is_daily_page_title` to `integrations.py`**

Add this function immediately before the `class NotionClient:` line in `src/wizard/integrations.py`:

```python
def _is_daily_page_title(title: str) -> bool:
    """Return True if title matches the daily-page format, e.g. 'Wednesday 9 April 2026'."""
    try:
        datetime.datetime.strptime(title, "%A %d %B %Y")
        return True
    except ValueError:
        return False
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_integrations.py::TestIsDailyPageTitle -xvs
```

Expected: all 2 tests pass.

---

## Task 2 — Fix 1b: `ensure_daily_page` scope (Tier 1)

**Files:**
- Modify: `src/wizard/integrations.py` (`ensure_daily_page` method)
- Modify: `tests/test_integrations.py` (new test)

- [ ] **Step 1: Write the failing test**

Add after `test_notion_ensure_daily_page_creates_and_archives` in `tests/test_integrations.py`:

```python
def test_notion_ensure_daily_page_leaves_non_daily_pages_alone():
    """Permanent (non-daily) pages under SISU Work must not be archived."""
    with patch("wizard.integrations._today_title", return_value="Friday 11 April 2026"):
        with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
            mock_instance = MagicMock()
            mock_notion_class.return_value = mock_instance
            mock_instance.blocks.children.list.return_value = {
                "results": [
                    _make_child_page_block("stale-daily-id", "Thursday 10 April 2026"),
                    _make_child_page_block("permanent-id", "SISU IQ Design"),
                    _make_child_page_block("another-perm-id", "Architecture Notes"),
                ]
            }
            mock_instance.pages.create.return_value = {"id": "new-daily-id"}
            mock_instance.pages.update.return_value = {}

            client = make_notion_client()
            result = client.ensure_daily_page()

    # Only the old daily page is archived — permanent pages left alone
    assert result.archived_count == 1
    archived_ids = [
        call.kwargs["page_id"]
        for call in mock_instance.pages.update.call_args_list
        if call.kwargs.get("archived") is True
    ]
    assert "stale-daily-id" in archived_ids
    assert "permanent-id" not in archived_ids
    assert "another-perm-id" not in archived_ids
```

- [ ] **Step 2: Run to confirm failure**

```
.venv/bin/python -m pytest tests/test_integrations.py::test_notion_ensure_daily_page_leaves_non_daily_pages_alone -xvs
```

Expected: FAIL — both permanent pages get archived under current behaviour.

- [ ] **Step 3: Fix `ensure_daily_page` in `integrations.py`**

Locate the loop inside `ensure_daily_page` that builds `stale_ids`. Replace:

```python
        stale_ids: list[str] = []
        for block in children:
            block_title = block.get("child_page", {}).get("title", "")
            if block_title == title:
                page_id = block["id"]
            else:
                stale_ids.append(block["id"])
```

With:

```python
        stale_ids: list[str] = []
        for block in children:
            block_title = block.get("child_page", {}).get("title", "")
            if block_title == title:
                page_id = block["id"]
            elif _is_daily_page_title(block_title):
                stale_ids.append(block["id"])
            # Non-daily pages are left untouched
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_integrations.py -xvs -k "daily"
```

Expected: all daily-page tests pass including the new one.

---

## Task 3 — Fix 2: Remove explicit `db.commit()` from `update_task` (Tier 1)

**Files:**
- Modify: `src/wizard/tools.py` (`update_task`)
- Modify: `tests/test_tools.py` (new test)

- [ ] **Step 1: Write the regression-guard test**

Add to `tests/test_tools.py`:

```python
async def test_update_task_outcome_writeback_called_when_elicited(db_session):
    """Outcome writeback must be called when elicitation returns text."""
    from wizard.tools import update_task
    from wizard.models import Task, TaskStatus, TaskPriority, TaskCategory, TaskState
    import datetime

    task = Task(
        name="Fix auth",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        notion_id="notion-page-123",
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    state = TaskState(
        task_id=task.id,
        note_count=0,
        decision_count=0,
        last_touched_at=datetime.datetime.now(),
        stale_days=0,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext(elicit_response="Shipped the fix.")
    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = MagicMock(ok=True, error=None)
    wb_mock.push_task_status_to_notion.return_value = MagicMock(ok=True, error=None, page_id="notion-page-123")
    wb_mock.append_task_outcome.return_value = MagicMock(ok=True, error=None)

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(ctx, task_id=task.id, status=TaskStatus.DONE)

    wb_mock.append_task_outcome.assert_called_once()
    call_args = wb_mock.append_task_outcome.call_args
    assert "Shipped the fix." in call_args[0][1]
    assert result.updated_fields == ["status"]
```

- [ ] **Step 2: Run to verify it passes (regression guard)**

```
.venv/bin/python -m pytest tests/test_tools.py::test_update_task_outcome_writeback_called_when_elicited -xvs
```

Expected: PASS (test establishes the expected behaviour before the code change).

- [ ] **Step 3: Remove explicit `db.commit()` from `update_task`**

In `src/wizard/tools.py`, inside the `update_task` function body, locate and **delete** exactly this line:

```python
            db.commit()
```

It appears after the elicitation block (after the `writeback().append_task_outcome(...)` call), before `status_writeback = None`. This is the only explicit `db.commit()` inside `update_task`. The context manager in `get_session` handles the commit on exit.

- [ ] **Step 4: Run the full tools test suite**

```
.venv/bin/python -m pytest tests/test_tools.py -xvs
```

Expected: all tests pass.

- [ ] **Step 5: Commit Tier 1**

```bash
git add src/wizard/integrations.py tests/test_integrations.py src/wizard/tools.py tests/test_tools.py
git commit -m "fix: critical — scope daily page archiving to date-formatted titles; remove double-commit in update_task"
```

---

## Task 4 — Fix 3: `query_compounding` session-boundary logic (Tier 2)

**Files:**
- Modify: `src/wizard/cli/analytics.py` (`query_compounding`)
- Modify: `tests/test_cli_analytics.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_analytics.py`:

```python
def test_query_compounding_empty_db_returns_zero(db_session):
    from wizard.cli.analytics import query_compounding
    import datetime
    result = query_compounding(db_session, datetime.date(2026, 1, 1), datetime.date(2026, 1, 7))
    assert result == 0.0


def test_query_compounding_no_prior_notes_returns_zero(db_session):
    """task_start exists in window and notes exist, but all notes are from this window."""
    import datetime as dt
    from wizard.cli.analytics import query_compounding
    from wizard.models import Note, NoteType, Task, TaskStatus, TaskCategory, TaskPriority, ToolCall

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    session_start_time = dt.datetime(2026, 1, 3, 9, 0, 0)
    # Note created AFTER the session starts — same window, not prior context
    db_session.add(Note(
        task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="first note", created_at=dt.datetime(2026, 1, 3, 10, 0, 0),
    ))
    db_session.add(ToolCall(tool_name="session_start", called_at=session_start_time, session_id=1))
    db_session.add(ToolCall(tool_name="task_start", called_at=dt.datetime(2026, 1, 3, 9, 5, 0), session_id=1))
    db_session.commit()

    result = query_compounding(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result == 0.0


def test_query_compounding_prior_session_notes_returns_nonzero(db_session):
    """Notes from before the window's first session indicate prior-session context."""
    import datetime as dt
    from wizard.cli.analytics import query_compounding
    from wizard.models import Note, NoteType, Task, TaskStatus, TaskCategory, TaskPriority, ToolCall

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    # Note from a prior session (before the window's first session_start)
    db_session.add(Note(
        task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="prior session note", created_at=dt.datetime(2025, 12, 20, 10, 0, 0),
    ))
    session_start_time = dt.datetime(2026, 1, 3, 9, 0, 0)
    db_session.add(ToolCall(tool_name="session_start", called_at=session_start_time, session_id=1))
    db_session.add(ToolCall(tool_name="task_start", called_at=dt.datetime(2026, 1, 3, 9, 5, 0), session_id=1))
    db_session.commit()

    result = query_compounding(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result == 1.0
```

- [ ] **Step 2: Run to confirm failures**

```
.venv/bin/python -m pytest tests/test_cli_analytics.py::test_query_compounding_no_prior_notes_returns_zero -xvs
```

Expected: FAIL — current code returns 1.0 because any note in the DB triggers compounding.

- [ ] **Step 3: Rewrite `query_compounding` in `analytics.py`**

Replace the entire `query_compounding` function body:

```python
def query_compounding(db, start: datetime.date, end: datetime.date) -> float:
    from sqlmodel import select
    from wizard.models import Note, ToolCall

    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    task_starts = db.exec(
        select(ToolCall).where(
            ToolCall.tool_name == "task_start",
            ToolCall.called_at >= start_dt,
            ToolCall.called_at <= end_dt,
        )
    ).all()

    if not task_starts:
        return 0.0

    # Find the earliest session_start in the window to use as the prior-context boundary.
    # Any note before this timestamp came from a previous session.
    session_starts = db.exec(
        select(ToolCall).where(
            ToolCall.tool_name == "session_start",
            ToolCall.called_at >= start_dt,
            ToolCall.called_at <= end_dt,
        )
    ).all()

    if not session_starts:
        return 0.0

    earliest_session_start = min(tc.called_at for tc in session_starts)

    prior_context_exists = (
        db.exec(select(Note).where(Note.created_at < earliest_session_start)).first()
        is not None
    )

    if not prior_context_exists:
        return 0.0

    compounding_count = sum(1 for tc in task_starts if tc.session_id is not None)
    return round(compounding_count / len(task_starts), 2)
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_cli_analytics.py -xvs -k "compounding"
```

Expected: all compounding tests pass.

---

## Task 5 — Fix 4: `query_tasks` ignores None task_id (Tier 2)

**Files:**
- Modify: `src/wizard/cli/analytics.py` (`query_tasks`)
- Modify: `tests/test_cli_analytics.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_analytics.py`:

```python
def test_query_tasks_ignores_session_summary_notes(db_session):
    """Notes with task_id=None must not inflate 'tasks worked'."""
    import datetime as dt
    from wizard.cli.analytics import query_tasks
    from wizard.models import Note, NoteType

    db_session.add(Note(
        task_id=None,
        note_type=NoteType.SESSION_SUMMARY,
        content="session wrap-up",
        created_at=dt.datetime(2026, 1, 3),
    ))
    db_session.commit()

    result = query_tasks(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result["worked"] == 0
    assert result["avg_notes_per_task"] == 0.0


def test_query_tasks_counts_only_task_notes(db_session):
    """task notes and non-task notes coexist — only task notes are counted."""
    import datetime as dt
    from wizard.cli.analytics import query_tasks
    from wizard.models import Note, NoteType, Task, TaskStatus, TaskCategory, TaskPriority

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    db_session.add(Note(
        task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="task note", created_at=dt.datetime(2026, 1, 3),
    ))
    db_session.add(Note(
        task_id=None, note_type=NoteType.SESSION_SUMMARY,
        content="session note", created_at=dt.datetime(2026, 1, 3),
    ))
    db_session.commit()

    result = query_tasks(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result["worked"] == 1
    assert result["avg_notes_per_task"] == 1.0
```

- [ ] **Step 2: Run to confirm failures**

```
.venv/bin/python -m pytest tests/test_cli_analytics.py::test_query_tasks_ignores_session_summary_notes -xvs
```

Expected: FAIL — `worked` is 1 because the None key is counted.

- [ ] **Step 3: Fix `query_tasks` in `analytics.py`**

Locate the loop in `query_tasks` that builds `task_note_counts`. Replace:

```python
    task_note_counts: dict[int, int] = {}
    for note in notes:
        task_note_counts[note.task_id] = task_note_counts.get(note.task_id, 0) + 1
```

With:

```python
    task_note_counts: dict[int, int] = {}
    for note in notes:
        if note.task_id is not None:
            task_note_counts[note.task_id] = task_note_counts.get(note.task_id, 0) + 1
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_cli_analytics.py -xvs
```

Expected: all analytics tests pass.

- [ ] **Step 5: Commit Tier 2**

```bash
git add src/wizard/cli/analytics.py tests/test_cli_analytics.py
git commit -m "fix: analytics — correct compounding session boundary; skip None task_id in query_tasks"
```

---

## Task 6 — Fix 5: `_check_notion_schema` uses schema variable (Tier 3)

**Files:**
- Modify: `src/wizard/cli/main.py` (`_check_notion_schema`)
- Modify: `tests/test_cli.py` (new test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_check_notion_schema_uses_schema_meeting_category_field(tmp_path, monkeypatch):
    """schema.meeting_category is used — not the hardcoded string 'Category'."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_db_id": "tasks-db",
            "meetings_db_id": "meetings-db",
            "notion_schema": {"meeting_category": "Meeting Type"},
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        "Task": "title", "Status": "status",
        "Priority": "select", "Due date": "date", "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title", "Date": "date",
        "Krisp URL": "url", "Summary": "rich_text",
        "Meeting Type": "multi_select",  # custom name, not "Category"
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.main import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is True, f"Expected pass but got: {msg}"
```

- [ ] **Step 2: Run to confirm failure**

```
.venv/bin/python -m pytest tests/test_cli.py::test_check_notion_schema_uses_schema_meeting_category_field -xvs
```

Expected: FAIL — current code checks for `"Category"`, not `"Meeting Type"`.

- [ ] **Step 3: Fix the hardcoded field name in `_check_notion_schema`**

In `src/wizard/cli/main.py`, inside `_check_notion_schema`, locate `meeting_fields` and change the last tuple:

```python
        ("Category", "multi_select"),
```

To:

```python
        (schema.meeting_category, "multi_select"),
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_cli.py -xvs -k "notion_schema"
```

Expected: all notion schema tests pass including the new one.

---

## Task 7 — Fix 6 + Fix 9: Docstring corrections (Tier 3)

**Files:**
- Modify: `src/wizard/models.py` (`Note.mental_model` field description)
- Modify: `src/wizard/tools.py` (`update_task` docstring)

No new tests — documentation-only changes.

- [ ] **Step 1: Fix `Note.mental_model` description in `models.py`**

Locate the `mental_model` field on the `Note` model. Replace:

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

With:

```python
    mental_model: str | None = Field(
        default=None,
        description=(
            "1-2 sentence causal abstraction written by the engineer. "
            "Soft cap 1500 chars at the application display layer."
        ),
    )
```

- [ ] **Step 2: Fix `update_task` docstring in `tools.py`**

Replace the Writebacks section of the `update_task` docstring:

```python
    """Atomically update task fields. Only provided (non-None) fields are updated.

    Raises ToolError if no fields are provided or task not found.

    Writebacks:
    - status: Jira + Notion
    - due_date: Notion only
    - priority: Notion only
    """
```

With:

```python
    """Atomically update task fields. Only provided (non-None) fields are updated.

    Raises ToolError if no fields are provided or task not found.

    Writebacks:
    - status: Jira + Notion
    - due_date: Notion only
    - priority: Notion only
    - name: local only (no external writeback)
    - source_url: local only (no external writeback)
    """
```

- [ ] **Step 3: Run the full test suite to verify nothing broken**

```
.venv/bin/python -m pytest tests/ -x -q
```

Expected: all tests pass.

---

## Task 8 — Fix 7: `task_start` returns notes oldest-first (Tier 3)

**Files:**
- Modify: `src/wizard/tools.py` (`task_start`, `prior_notes` line)
- Modify: `src/wizard/schemas.py` (`TaskStartResponse.prior_notes` comment)
- Modify: `tests/test_tools.py` (new test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tools.py`:

```python
async def test_task_start_returns_prior_notes_oldest_first(db_session):
    """prior_notes must be ordered oldest-first (matching rewind_task convention)."""
    from wizard.tools import task_start
    from wizard.models import Task, TaskStatus, TaskPriority, TaskCategory, Note, NoteType, TaskState
    import datetime

    task = Task(
        name="Fix auth",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    state = TaskState(
        task_id=task.id,
        note_count=2,
        decision_count=0,
        last_touched_at=datetime.datetime.now(),
        stale_days=0,
    )
    db_session.add(state)

    older = Note(
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="older note",
        created_at=datetime.datetime(2026, 1, 1, 10, 0, 0),
    )
    newer = Note(
        task_id=task.id,
        note_type=NoteType.DECISION,
        content="newer note",
        created_at=datetime.datetime(2026, 1, 3, 10, 0, 0),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await task_start(ctx, task_id=task.id)

    assert len(result.prior_notes) == 2
    assert result.prior_notes[0].content == "older note"
    assert result.prior_notes[1].content == "newer note"
```

- [ ] **Step 2: Run to confirm failure**

```
.venv/bin/python -m pytest tests/test_tools.py::test_task_start_returns_prior_notes_oldest_first -xvs
```

Expected: FAIL — notes come back newest-first in current code.

- [ ] **Step 3: Fix `task_start` in `tools.py`**

In the `task_start` function, locate:

```python
            prior_notes = [NoteDetail.from_model(n) for n in notes]
```

Replace with:

```python
            prior_notes = [NoteDetail.from_model(n) for n in reversed(notes) if n.id is not None]
```

- [ ] **Step 4: Update `TaskStartResponse.prior_notes` comment in `schemas.py`**

Locate `TaskStartResponse` in `src/wizard/schemas.py` and update the inline comment:

```python
class TaskStartResponse(BaseModel):
    task: TaskContext
    compounding: bool  # True if prior notes exist for this task
    notes_by_type: dict[str, int]  # {"investigation": 3, "decision": 1}
    prior_notes: list[NoteDetail]  # all notes, oldest first
    latest_mental_model: str | None = None
```

(Change `# all notes, oldest first` — the existing comment may say something different; update it to match this.)

- [ ] **Step 5: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_tools.py::test_task_start_returns_prior_notes_oldest_first -xvs
```

Expected: PASS.

---

## Task 9 — Fix 8: `ToolCall.called_at` naive datetime (Tier 3)

**Files:**
- Modify: `src/wizard/models.py` (`ToolCall.called_at` field)
- Modify: `tests/test_models.py` (new test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_toolcall_called_at_is_naive():
    """ToolCall.called_at default must be timezone-naive (consistent with SQLite storage)."""
    from wizard.models import ToolCall
    tc = ToolCall(tool_name="test_tool")
    assert tc.called_at.tzinfo is None
```

- [ ] **Step 2: Run to confirm failure**

```
.venv/bin/python -m pytest tests/test_models.py::test_toolcall_called_at_is_naive -xvs
```

Expected: FAIL — `tc.called_at.tzinfo` is `datetime.timezone.utc`, not `None`.

- [ ] **Step 3: Fix `ToolCall.called_at` in `models.py`**

Locate the `ToolCall` class and change `called_at`:

```python
    called_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc), index=True
    )
```

To:

```python
    called_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, index=True
    )
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_models.py::test_toolcall_called_at_is_naive -xvs
```

Expected: PASS.

- [ ] **Step 5: Commit Tier 3**

```bash
git add src/wizard/cli/main.py src/wizard/models.py src/wizard/tools.py src/wizard/schemas.py tests/test_cli.py tests/test_tools.py tests/test_models.py
git commit -m "fix: medium — schema variable in doctor check; docstrings; note ordering; naive ToolCall timestamp"
```

---

## Task 10 — Fix 10: Replace `assert` with `ToolError` in tools (Tier 4)

**Files:**
- Modify: `src/wizard/tools.py` (seven assertions across six functions)

No new tests — defensive guards for flush-time invariants.

- [ ] **Step 1: Replace `assert session.id is not None` in `session_start`**

Find:
```python
        assert session.id is not None
```
Replace with:
```python
        if session.id is None:
            raise ToolError("Internal error: session was not assigned an id after flush")
```

- [ ] **Step 2: Replace `assert saved.id is not None` in `save_note`**

Find:
```python
            assert saved.id is not None
```
Replace with:
```python
            if saved.id is None:
                raise ToolError("Internal error: note was not assigned an id after flush")
```

- [ ] **Step 3: Replace `assert meeting.id is not None` in `get_meeting`**

Find (in `get_meeting`):
```python
            assert meeting.id is not None
```
Replace with:
```python
            if meeting.id is None:
                raise ToolError("Internal error: meeting was not assigned an id after flush")
```

- [ ] **Step 4: Replace asserts in `save_meeting_summary`**

Find (first assert in `save_meeting_summary`):
```python
            assert meeting.id is not None
```
Replace with:
```python
            if meeting.id is None:
                raise ToolError("Internal error: meeting was not assigned an id after flush")
```

Find (second assert in `save_meeting_summary`):
```python
            assert saved.id is not None
```
Replace with:
```python
            if saved.id is None:
                raise ToolError("Internal error: note was not assigned an id after flush")
```

- [ ] **Step 5: Replace `assert session.id is not None` in `session_end`**

Find (in `session_end`, after `db.refresh(session)`):
```python
            assert session.id is not None
```
Replace with:
```python
            if session.id is None:
                raise ToolError("Internal error: session was not assigned an id after flush")
```

- [ ] **Step 6: Replace `assert meeting.id is not None` in `ingest_meeting`**

Find (in `ingest_meeting`):
```python
        assert meeting.id is not None
```
Replace with:
```python
        if meeting.id is None:
            raise ToolError("Internal error: meeting was not assigned an id after flush")
```

- [ ] **Step 7: Replace `assert task.id is not None` in `create_task`**

Find (in `create_task`):
```python
        assert task.id is not None
```
Replace with:
```python
        if task.id is None:
            raise ToolError("Internal error: task was not assigned an id after flush")
```

- [ ] **Step 8: Run the full tools test suite**

```
.venv/bin/python -m pytest tests/test_tools.py -xvs
```

Expected: all tests pass.

---

## Task 11 — Fix 11: `what_am_i_missing` rule 6 overlap (Tier 4)

**Files:**
- Modify: `src/wizard/tools.py` (`what_am_i_missing`, rule 6 condition)
- Modify: `tests/test_tools.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tools.py`:

```python
async def test_what_am_i_missing_stale_2_days_fires_lost_context_not_stale(db_session):
    """stale_days=2 with notes → lost_context fires; stale must NOT fire (threshold is >= 3)."""
    from wizard.tools import what_am_i_missing
    from wizard.models import Task, TaskStatus, TaskPriority, TaskCategory, Note, NoteType, TaskState
    import datetime

    task = Task(name="T", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="some work")
    db_session.add(note)
    db_session.flush()
    db_session.refresh(note)

    last_note = datetime.datetime.now() - datetime.timedelta(days=2)
    state = TaskState(
        task_id=task.id,
        note_count=1,
        decision_count=0,
        last_note_at=last_note,
        last_touched_at=last_note,
        stale_days=2,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await what_am_i_missing(ctx, task_id=task.id)

    signal_types = [s.type for s in result.signals]
    assert "lost_context" in signal_types
    assert "stale" not in signal_types


async def test_what_am_i_missing_stale_3_days_fires_stale_not_lost_context(db_session):
    """stale_days=3 with notes → stale fires; lost_context must NOT fire (no double-signal)."""
    from wizard.tools import what_am_i_missing
    from wizard.models import Task, TaskStatus, TaskPriority, TaskCategory, Note, NoteType, TaskState
    import datetime

    task = Task(name="T", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="some work")
    db_session.add(note)
    db_session.flush()
    db_session.refresh(note)

    last_note = datetime.datetime.now() - datetime.timedelta(days=3)
    state = TaskState(
        task_id=task.id,
        note_count=1,
        decision_count=0,
        last_note_at=last_note,
        last_touched_at=last_note,
        stale_days=3,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await what_am_i_missing(ctx, task_id=task.id)

    signal_types = [s.type for s in result.signals]
    assert "stale" in signal_types
    assert "lost_context" not in signal_types
```

- [ ] **Step 2: Run to confirm failures**

```
.venv/bin/python -m pytest tests/test_tools.py::test_what_am_i_missing_stale_3_days_fires_stale_not_lost_context -xvs
```

Expected: FAIL — both `stale` and `lost_context` fire at 3 days in current code.

- [ ] **Step 3: Fix rule 6 in `what_am_i_missing`**

Locate rule 6 in the `what_am_i_missing` function:

```python
        # Rule 6: has notes but stale for 2+ days
        if task_state.last_note_at is not None and sd >= 2:
            signals.append(
                Signal(
                    type="lost_context",
                    severity="medium",
                    message="Context may be degrading due to inactivity",
                )
            )
```

Replace with:

```python
        # Rule 6: has notes and stale 2-3 days (rule 2 covers >= 3 days; avoid double-signal)
        if task_state.last_note_at is not None and 2 <= sd < 3:
            signals.append(
                Signal(
                    type="lost_context",
                    severity="medium",
                    message="Context may be degrading due to inactivity",
                )
            )
```

- [ ] **Step 4: Run to confirm pass**

```
.venv/bin/python -m pytest tests/test_tools.py::test_what_am_i_missing_stale_2_days_fires_lost_context_not_stale tests/test_tools.py::test_what_am_i_missing_stale_3_days_fires_stale_not_lost_context -xvs
```

Expected: both pass.

- [ ] **Step 5: Run the full test suite**

```
.venv/bin/python -m pytest tests/ -x -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Tier 4**

```bash
git add src/wizard/tools.py tests/test_tools.py
git commit -m "fix: low — assert to ToolError; eliminate what_am_i_missing rule 6 double-signal"
```

---

## Self-Review

**Spec coverage:**
- Fix 1 (`_is_daily_page_title` + `ensure_daily_page`) → Tasks 1–2 ✓
- Fix 2 (`update_task` double-commit) → Task 3 ✓
- Fix 3 (`query_compounding`) → Task 4 ✓
- Fix 4 (`query_tasks` None key) → Task 5 ✓
- Fix 5 (`_check_notion_schema` hardcoded) → Task 6 ✓
- Fix 6 (`Note.mental_model` docstring) → Task 7 ✓
- Fix 7 (`task_start` note ordering) → Task 8 ✓
- Fix 8 (`ToolCall.called_at` timezone) → Task 9 ✓
- Fix 9 (`update_task` docstring) → Task 7 ✓
- Fix 10 (`assert` → `ToolError`) → Task 10 ✓
- Fix 11 (`what_am_i_missing` rule overlap) → Task 11 ✓

**Placeholder scan:** No TBDs, no "similar to above". All code blocks are complete. ✓

**Type consistency:** `NoteDetail.from_model`, `TaskState`, `MockContext`, `_patch_tools` — all used consistently with their definitions in `helpers.py` and `conftest.py`. ✓

**Tier commit check:** Tier 1 after Task 3 step 5, Tier 2 after Task 5 step 5, Tier 3 after Task 9 step 5, Tier 4 after Task 11 step 6. ✓
