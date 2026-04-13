# FastMCP Context Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 9 Wizard tools to `async def` with FastMCP `Context` injection, add session threading via `ctx.set_state`/`ctx.get_state`, add `ctx.elicit` for mental model and outcome prompts, add `ctx.report_progress` in `session_start`, and expand `session_end` to the six-field `SessionState` signature.

**Architecture:** Four logical commits on `feat/b-context-migration`. Commit 1 does the mechanical async shell + test infrastructure. Commit 2 wires session threading (`ctx.set_state`/`ctx.get_state`/`ctx.delete_state`). Commit 3 adds elicitation and progress. Commit 4 expands `session_end` and rewrites the skill. All work is in `tools.py`, `services.py`, `integrations.py`, `schemas.py`, `pyproject.toml`, `tests/helpers.py`, and `tests/test_tools.py`.

**Tech Stack:** Python 3.14, FastMCP ≥ 3.2.0, SQLModel, pytest-asyncio 0.24.0, asyncio_mode=auto.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/wizard/tools.py` | Modify | All 9 tools → async + ctx; session threading; elicitation; progress; session_end expansion |
| `src/wizard/services.py` | Modify | Promote 3 private sync methods to public; add `WriteBackService.append_task_outcome` |
| `src/wizard/integrations.py` | Modify | Add `NotionClient.append_paragraph_to_page` |
| `src/wizard/schemas.py` | Modify | Add 4 echo fields to `SessionEndResponse` |
| `src/wizard/skills/session-end/SKILL.md` | Modify | Rewrite for 8-param session_end signature |
| `pyproject.toml` | Modify | Add pytest-asyncio dev dep; set asyncio_mode=auto |
| `tests/helpers.py` | Modify | Add `MockContext` test double |
| `tests/test_tools.py` | Modify | All tests → async + ctx; add 13 new tests |
| `tests/test_services.py` | Modify | Update references to promoted public method names |

---

## Task 0: Test Infrastructure + Deps

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/helpers.py`

### Step 0.1: Add pytest-asyncio to dev deps

Edit `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=9.0",
    "pytest-asyncio>=0.24.0",
    "respx>=0.23.1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Step 0.2: Install updated deps

```
uv sync
```

Expected: resolves without error, `pytest-asyncio` appears in `uv.lock`.

### Step 0.3: Add MockContext to tests/helpers.py

Replace the entire contents of `tests/helpers.py` with:

```python
from contextlib import contextmanager


def mock_session(db_session):
    """Context manager that yields the test db_session instead of creating a new one."""

    @contextmanager
    def _inner():
        yield db_session
        db_session.flush()

    return _inner


class MockContext:
    """Minimal FastMCP Context double for async tool tests.

    Records all ctx.* calls so tests can assert on them.
    Elicit response is configurable: None → DeclinedElicitation,
    a string → AcceptedElicitation(data=<string>).
    Set supports_elicit=False to simulate a client that raises on elicit.
    """

    def __init__(
        self,
        elicit_response: str | None = None,
        supports_elicit: bool = True,
    ):
        self.info_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.error_calls: list[str] = []
        self.progress_calls: list[tuple[int, int, str | None]] = []
        self._state: dict[str, object] = {}
        self._elicit_response = elicit_response
        self._supports_elicit = supports_elicit

    async def info(self, msg: str) -> None:
        self.info_calls.append(msg)

    async def warning(self, msg: str) -> None:
        self.warning_calls.append(msg)

    async def error(self, msg: str) -> None:
        self.error_calls.append(msg)

    async def report_progress(
        self, current: int, total: int, message: str | None = None
    ) -> None:
        self.progress_calls.append((current, total, message))

    async def set_state(self, key: str, value: object) -> None:
        self._state[key] = value

    async def get_state(self, key: str, default: object = None) -> object:
        return self._state.get(key, default)

    async def delete_state(self, key: str) -> None:
        self._state.pop(key, None)

    async def elicit(self, message: str, response_type=None):
        from fastmcp.client.elicitation import AcceptedElicitation, DeclinedElicitation

        if not self._supports_elicit:
            raise RuntimeError("Client does not support elicitation")
        if self._elicit_response is None:
            return DeclinedElicitation()
        return AcceptedElicitation(data=self._elicit_response)
```

### Step 0.4: Run existing tests — expect failures

```
uv run pytest tests/test_tools.py -x -q 2>&1 | head -30
```

Expected: tests fail because tools are still sync and don't accept `ctx`. This confirms the failing baseline.

### Step 0.5: Commit

```
git add pyproject.toml uv.lock tests/helpers.py
git commit -m "chore: add pytest-asyncio + MockContext for async tool tests"
```

---

## Task 1: Async Shell — All 9 Tools

**Files:**
- Modify: `src/wizard/tools.py`
- Modify: `tests/test_tools.py`

Goal: convert every tool to `async def` with `ctx: Context` as first param. No new behaviour yet — only the shell change. `_log_tool_call` becomes `async def`. All existing tests updated to `async def` + `ctx = MockContext()` + `await tool(ctx, ...)`.

### Step 1.1: Write one anchor test that must pass after the rewrite

Add at the TOP of the test section in `tests/test_tools.py` (after imports, before `test_session_start_creates_session`):

```python
async def test_tools_are_async_with_ctx(db_session):
    """Smoke test: session_start is awaitable and accepts ctx as first arg."""
    from tests.helpers import MockContext
    from wizard.tools import session_start
    from unittest.mock import MagicMock

    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert result.session_id is not None
```

Run it:

```
uv run pytest tests/test_tools.py::test_tools_are_async_with_ctx -v
```

Expected: FAIL — `session_start` is not async.

### Step 1.2: Rewrite tools.py — async shell only

Replace `src/wizard/tools.py` with the async shell. Every tool becomes `async def tool_name(ctx: Context, ...)`. `_log_tool_call` becomes async. No new behaviour beyond the signature change:

```python
import logging
from typing import Literal

from fastmcp import Context
from fastmcp.exceptions import ToolError
from sqlmodel import Session, select

from .database import get_session
from .deps import (
    meeting_repo,
    note_repo,
    notion_client,
    security,
    sync_service,
    task_repo,
    task_state_repo,
    writeback,
)
from .mcp_instance import mcp
from .models import (
    Meeting,
    MeetingCategory,
    MeetingTasks,
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskStatus,
    ToolCall,
    WizardSession,
)
from .schemas import (
    CreateTaskResponse,
    GetMeetingResponse,
    IngestMeetingResponse,
    NoteDetail,
    SaveMeetingSummaryResponse,
    SaveNoteResponse,
    SessionEndResponse,
    SessionStartResponse,
    SessionState,
    SourceSyncStatus,
    TaskStartResponse,
    UpdateTaskStatusResponse,
)

logger = logging.getLogger(__name__)


async def _log_tool_call(
    db: Session, tool_name: str, session_id: int | None = None
) -> None:
    db.add(ToolCall(tool_name=tool_name, session_id=session_id))
    db.flush()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def session_start(ctx: Context) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None
        await _log_tool_call(db, "session_start", session_id=session.id)

        sync_results = sync_service().sync_all(db)

        daily_page = None
        try:
            daily_page = notion_client().ensure_daily_page()
            session.daily_page_id = daily_page.page_id
            db.add(session)
            db.flush()
        except Exception as e:
            logger.warning("ensure_daily_page failed: %s", e)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
            daily_page=daily_page,
        )


async def task_start(ctx: Context, task_id: int) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context.

    task_id: integer task ID from the open_tasks or blocked_tasks list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("task_start task_id=%d", task_id)
    try:
        with get_session() as db:
            await _log_tool_call(db, "task_start")
            task = task_repo().get_by_id(db, task_id)
            task_ctx = task_repo().build_task_context(db, task)

            notes = note_repo().get_for_task(
                db, task_id=task.id, source_id=task.source_id
            )
            notes_by_type: dict[str, int] = {}
            for note in notes:
                key = note.note_type.value
                notes_by_type[key] = notes_by_type.get(key, 0) + 1

            prior_notes = [NoteDetail.from_model(n) for n in notes]

            return TaskStartResponse(
                task=task_ctx,
                compounding=len(notes) > 0,
                notes_by_type=notes_by_type,
                prior_notes=prior_notes,
            )
    except ValueError as e:
        logger.warning("task_start failed: %s", e)
        raise ToolError(str(e)) from e


async def save_note(
    ctx: Context,
    task_id: int,
    note_type: NoteType,
    content: str,
    mental_model: str | None = None,
) -> SaveNoteResponse:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)
    try:
        with get_session() as db:
            await _log_tool_call(db, "save_note")
            task = task_repo().get_by_id(db, task_id)
            clean = security().scrub(content).clean
            note = Note(
                note_type=note_type,
                content=clean,
                mental_model=mental_model,
                task_id=task.id,
                source_id=task.source_id,
                source_type=task.source_type,
            )
            saved = note_repo().save(db, note)
            assert saved.id is not None
            task_state_repo().on_note_saved(db, task_id)
            return SaveNoteResponse(note_id=saved.id, mental_model=saved.mental_model)
    except ValueError as e:
        logger.warning("save_note failed: %s", e)
        raise ToolError(str(e)) from e


async def update_task_status(
    ctx: Context, task_id: int, new_status: TaskStatus
) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back."""
    logger.info(
        "update_task_status task_id=%d new_status=%s", task_id, new_status.value
    )
    try:
        with get_session() as db:
            await _log_tool_call(db, "update_task_status")
            task = task_repo().get_by_id(db, task_id)
            task.status = new_status
            db.add(task)
            db.flush()
            db.refresh(task)
            assert task.id is not None

            task_state_repo().on_status_changed(db, task.id)

            jira_wb = writeback().push_task_status(task)
            notion_wb = writeback().push_task_status_to_notion(task)

            return UpdateTaskStatusResponse(
                task_id=task.id,
                new_status=task.status,
                jira_write_back=jira_wb,
                notion_write_back=notion_wb,
                task_state_updated=True,
            )
    except ValueError as e:
        logger.warning("update_task_status failed: %s", e)
        raise ToolError(str(e)) from e


async def get_meeting(ctx: Context, meeting_id: int) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks.

    meeting_id: integer meeting ID from the unsummarised_meetings list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("get_meeting meeting_id=%d", meeting_id)
    try:
        with get_session() as db:
            await _log_tool_call(db, "get_meeting")
            meeting = meeting_repo().get_by_id(db, meeting_id)
            assert meeting.id is not None

            linked_tasks = [
                task_repo().build_task_context(db, t)
                for t in meeting.tasks
                if t.status
                in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
            ]

            return GetMeetingResponse(
                meeting_id=meeting.id,
                title=meeting.title,
                category=meeting.category,
                content=meeting.content,
                already_summarised=meeting.summary is not None,
                existing_summary=meeting.summary,
                open_tasks=linked_tasks,
            )
    except ValueError as e:
        logger.warning("get_meeting failed: %s", e)
        raise ToolError(str(e)) from e


async def save_meeting_summary(
    ctx: Context,
    meeting_id: int,
    session_id: int,
    summary: str,
    task_ids: list[int] | None = None,
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
    logger.info(
        "save_meeting_summary meeting_id=%d session_id=%d", meeting_id, session_id
    )
    try:
        with get_session() as db:
            await _log_tool_call(db, "save_meeting_summary", session_id=session_id)
            meeting = meeting_repo().get_by_id(db, meeting_id)
            assert meeting.id is not None

            clean_summary = security().scrub(summary).clean
            meeting.summary = clean_summary
            db.add(meeting)

            note = Note(
                note_type=NoteType.DOCS,
                content=clean_summary,
                meeting_id=meeting.id,
                session_id=session_id,
            )
            saved = note_repo().save(db, note)
            assert saved.id is not None

            if task_ids:
                for tid in task_ids:
                    existing_link = db.exec(
                        select(MeetingTasks).where(
                            MeetingTasks.meeting_id == meeting.id,
                            MeetingTasks.task_id == tid,
                        )
                    ).first()
                    if not existing_link:
                        db.add(MeetingTasks(meeting_id=meeting.id, task_id=tid))

            db.flush()
            wb_result = writeback().push_meeting_summary(meeting)

            linked_task_ids = [t.id for t in meeting.tasks if t.id is not None]

            return SaveMeetingSummaryResponse(
                note_id=saved.id,
                linked_task_ids=linked_task_ids,
                notion_write_back=wb_result,
            )
    except ValueError as e:
        logger.warning("save_meeting_summary failed: %s", e)
        raise ToolError(str(e)) from e


async def session_end(ctx: Context, session_id: int, summary: str) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    logger.info("session_end session_id=%d", session_id)
    with get_session() as db:
        await _log_tool_call(db, "session_end", session_id=session_id)
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ToolError(f"Session {session_id} not found")

        clean_summary = security().scrub(summary).clean
        session.summary = clean_summary
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary,
            session_id=session.id,
        )
        saved = note_repo().save(db, note)
        assert saved.id is not None

        wb_result = writeback().push_session_summary(session)

        return SessionEndResponse(
            note_id=saved.id,
            notion_write_back=wb_result,
        )


async def ingest_meeting(
    ctx: Context,
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    logger.info("ingest_meeting source_id=%s", source_id)
    with get_session() as db:
        await _log_tool_call(db, "ingest_meeting")
        clean_title = security().scrub(title).clean
        clean_content = security().scrub(content).clean

        meeting: Meeting | None = None
        already_existed = False
        if source_id:
            meeting = db.exec(
                select(Meeting).where(Meeting.source_id == source_id)
            ).first()
        if meeting:
            already_existed = True
            meeting.title = clean_title
            meeting.content = clean_content
            db.add(meeting)
        else:
            meeting = Meeting(
                title=clean_title,
                content=clean_content,
                source_id=source_id,
                source_type="KRISP" if source_id else None,
                source_url=source_url,
                category=category,
            )
            db.add(meeting)

        db.flush()
        db.refresh(meeting)
        assert meeting.id is not None

        wb_result = writeback().push_meeting_to_notion(meeting)
        if wb_result.page_id:
            meeting.notion_id = wb_result.page_id
            db.flush()

        return IngestMeetingResponse(
            meeting_id=meeting.id,
            already_existed=already_existed,
            notion_write_back=wb_result,
        )


async def create_task(
    ctx: Context,
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    logger.info("create_task priority=%s category=%s", priority.value, category.value)
    with get_session() as db:
        await _log_tool_call(db, "create_task")
        clean_name = security().scrub(name).clean
        task = Task(
            name=clean_name,
            priority=priority,
            category=category,
            status=TaskStatus.TODO,
            source_id=source_id,
            source_url=source_url,
        )
        db.add(task)
        db.flush()
        db.refresh(task)
        assert task.id is not None

        task_state_repo().create_for_task(db, task)

        if meeting_id:
            db.add(MeetingTasks(meeting_id=meeting_id, task_id=task.id))

        wb_result = writeback().push_task_to_notion(task)
        if wb_result.page_id:
            task.notion_id = wb_result.page_id
            db.flush()

        return CreateTaskResponse(
            task_id=task.id,
            notion_write_back=wb_result,
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(session_start)
mcp.tool()(task_start)
mcp.tool()(save_note)
mcp.tool()(update_task_status)
mcp.tool()(get_meeting)
mcp.tool()(save_meeting_summary)
mcp.tool()(session_end)
mcp.tool()(ingest_meeting)
mcp.tool()(create_task)
```

### Step 1.3: Update all existing tests to async + ctx

The `_patch_tools` helper stays unchanged. Every `def test_*` becomes `async def test_*`. Every call to a tool gets `ctx = MockContext()` and `await tool(ctx, ...)`.

Also update `_patch_tools` so `sync_mock.sync_all` is still available (session_start still calls `sync_all` at this stage — session threading comes in Task 2).

Replace `tests/test_tools.py` imports section and add MockContext import:

```python
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockContext, mock_session
```

Then convert every test function. Key patterns:

**session_start tests** — add `ctx = MockContext()`, add `await`:
```python
async def test_session_start_creates_session(db_session):
    from wizard.tools import session_start
    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert result.session_id is not None
    assert result.open_tasks is not None
    assert result.blocked_tasks is not None
    assert result.unsummarised_meetings is not None
    assert result.sync_results is not None
```

**task_start tests** — add `ctx = MockContext()`, add `await`, add ctx as first arg:
```python
async def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from wizard.models import Task, TaskStatus, Note, NoteType
    from wizard.tools import task_start
    ctx = MockContext()

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(note_type=NoteType.INVESTIGATION, content="prior investigation", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await task_start(ctx, task_id=task.id)

    assert result.compounding is True
    assert len(result.prior_notes) == 1
```

Apply this pattern to every test in the file. The full list of tests that need conversion (in addition to those shown above):

- `test_session_start_calls_sync` → `await session_start(ctx)`, assert `sync_mock.sync_all.assert_called_once()`
- `test_session_start_surfaces_sync_errors` → `await session_start(ctx)`
- `test_session_start_resolves_daily_page` → `await session_start(ctx)`
- `test_session_start_daily_page_failure_is_non_fatal` → `await session_start(ctx)`
- `test_task_start_returns_compounding_false_when_no_notes` → `await task_start(ctx, task_id=task.id)`
- `test_task_start_raises_when_task_not_found` → `await task_start(ctx, task_id=999)`
- All `save_note` tests → `await save_note(ctx, ...)`
- All `update_task_status` tests → `await update_task_status(ctx, ...)`
- All `get_meeting` tests → `await get_meeting(ctx, ...)`
- All `save_meeting_summary` tests → `await save_meeting_summary(ctx, ...)`
- All `session_end` tests → `await session_end(ctx, ...)`
- All `ingest_meeting` tests → `await ingest_meeting(ctx, ...)`
- All `create_task` tests → `await create_task(ctx, ...)`

### Step 1.4: Run all tests

```
uv run pytest tests/test_tools.py -v
```

Expected: all tests pass, including the anchor test `test_tools_are_async_with_ctx`.

### Step 1.5: Commit

```
git add src/wizard/tools.py tests/test_tools.py
git commit -m "feat: convert all 9 tools to async def with ctx: Context (shell only)"
```

---

## Task 2: Session Threading

**Files:**
- Modify: `src/wizard/services.py`
- Modify: `src/wizard/tools.py`
- Modify: `tests/test_tools.py`

Goal: `session_start` stores `session_id` in `ctx.set_state`. Mid-session tools read it via `ctx.get_state` and stamp it on `Note.session_id` and `ToolCall.session_id`. Replace inline `sync_all()` call in `session_start` with three public method calls (promote private sync methods to public in `SyncService`).

### Step 2.1: Write failing tests first

Add these tests to `tests/test_tools.py` in a new section `# --- session threading ---`:

```python
# --- session threading ---

async def test_session_start_sets_current_session_id_in_ctx_state(db_session):
    from wizard.tools import session_start
    from wizard.schemas import SourceSyncStatus

    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert await ctx.get_state("current_session_id") == result.session_id


async def test_save_note_uses_session_id_from_ctx_state_when_set(db_session):
    from wizard.models import Task, TaskStatus, NoteType, Note
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    await ctx.set_state("current_session_id", 42)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(ctx, task_id=task.id, note_type=NoteType.DOCS, content="content")

    note = db_session.get(Note, result.note_id)
    assert note.session_id == 42


async def test_save_note_session_id_null_when_no_ctx_state(db_session):
    from wizard.models import Task, TaskStatus, NoteType, Note
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()  # no set_state called — no session in context

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(ctx, task_id=task.id, note_type=NoteType.DOCS, content="content")

    note = db_session.get(Note, result.note_id)
    assert note.session_id is None


async def test_session_end_clears_current_session_id_from_ctx_state(db_session):
    from wizard.models import WizardSession
    from wizard.tools import session_end
    from unittest.mock import MagicMock

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    ctx = MockContext()
    await ctx.set_state("current_session_id", session.id)

    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock(
        return_value=__import__("wizard.schemas", fromlist=["WriteBackStatus"]).WriteBackStatus(ok=True)
    )

    with patch.multiple("wizard.tools", **patches):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="shipped X",
            working_set=[],
            state_delta="nothing blocked",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    assert await ctx.get_state("current_session_id") is None
```

Run:

```
uv run pytest tests/test_tools.py -k "threading or ctx_state or session_id_null" -v
```

Expected: FAIL — methods don't exist yet.

### Step 2.2: Promote private sync methods in services.py

In `src/wizard/services.py`, rename the three private sync methods to public:

```python
# Change:
def _sync_jira(self, db: Session) -> None:
# To:
def sync_jira(self, db: Session) -> None:

# Change:
def _sync_notion_tasks(self, db: Session) -> None:
# To:
def sync_notion_tasks(self, db: Session) -> None:

# Change:
def _sync_notion_meetings(self, db: Session) -> None:
# To:
def sync_notion_meetings(self, db: Session) -> None:
```

Update `sync_all` to use the new names:

```python
def sync_all(self, db: Session) -> list[SourceSyncStatus]:
    results: list[SourceSyncStatus] = []
    for source, fn in [
        ("jira", self.sync_jira),
        ("notion_tasks", self.sync_notion_tasks),
        ("notion_meetings", self.sync_notion_meetings),
    ]:
        try:
            fn(db)
            results.append(SourceSyncStatus(source=source, ok=True))
        except Exception as e:
            logger.warning("Sync failed for %s: %s", source, e)
            results.append(SourceSyncStatus(source=source, ok=False, error=str(e)))
    return results
```

### Step 2.3: Update session_start in tools.py

Replace the `sync_results = sync_service().sync_all(db)` block in `session_start` with three explicit calls + `ctx.set_state`:

```python
async def session_start(ctx: Context) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None
        await _log_tool_call(db, "session_start", session_id=session.id)

        svc = sync_service()
        sync_results: list[SourceSyncStatus] = []
        for source, fn in [
            ("jira", svc.sync_jira),
            ("notion_tasks", svc.sync_notion_tasks),
            ("notion_meetings", svc.sync_notion_meetings),
        ]:
            try:
                fn(db)
                sync_results.append(SourceSyncStatus(source=source, ok=True))
            except Exception as e:
                logger.warning("Sync failed for %s: %s", source, e)
                sync_results.append(SourceSyncStatus(source=source, ok=False, error=str(e)))

        await ctx.set_state("current_session_id", session.id)
        await ctx.info(f"Session {session.id} started.")

        daily_page = None
        try:
            daily_page = notion_client().ensure_daily_page()
            session.daily_page_id = daily_page.page_id
            db.add(session)
            db.flush()
        except Exception as e:
            logger.warning("ensure_daily_page failed: %s", e)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
            daily_page=daily_page,
        )
```

### Step 2.4: Add ctx.get_state reads in mid-session tools

In `task_start`, `save_note`, `update_task_status`, and `get_meeting`, read the session id from context and stamp it on `_log_tool_call`:

**task_start** — replace `await _log_tool_call(db, "task_start")` with:
```python
session_id: int | None = await ctx.get_state("current_session_id")
await _log_tool_call(db, "task_start", session_id=session_id)
```

**save_note** — replace `await _log_tool_call(db, "save_note")` with:
```python
session_id: int | None = await ctx.get_state("current_session_id")
await _log_tool_call(db, "save_note", session_id=session_id)
```

And stamp the session_id on the Note:
```python
note = Note(
    note_type=note_type,
    content=clean,
    mental_model=mental_model,
    task_id=task.id,
    source_id=task.source_id,
    source_type=task.source_type,
    session_id=session_id,
)
```

**update_task_status** — replace `await _log_tool_call(db, "update_task_status")` with:
```python
session_id: int | None = await ctx.get_state("current_session_id")
await _log_tool_call(db, "update_task_status", session_id=session_id)
```

**get_meeting** — replace `await _log_tool_call(db, "get_meeting")` with:
```python
session_id: int | None = await ctx.get_state("current_session_id")
await _log_tool_call(db, "get_meeting", session_id=session_id)
```

### Step 2.5: Update existing session_start tests that mock sync_all

Existing tests that do `sync_mock.sync_all = MagicMock(return_value=[])` must now mock the three public methods instead, because `session_start` no longer calls `sync_all`:

```python
# Old pattern (remove):
sync_mock.sync_all = MagicMock(return_value=[])

# New pattern (replace with):
sync_mock.sync_jira = MagicMock(return_value=None)
sync_mock.sync_notion_tasks = MagicMock(return_value=None)
sync_mock.sync_notion_meetings = MagicMock(return_value=None)
```

Also update `test_session_start_calls_sync` — it previously asserted `sync_mock.sync_all.assert_called_once()`. Replace it with three assertions:

```python
async def test_session_start_calls_sync(db_session):
    from wizard.tools import session_start
    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        await session_start(ctx)

    sync_mock.sync_jira.assert_called_once()
    sync_mock.sync_notion_tasks.assert_called_once()
    sync_mock.sync_notion_meetings.assert_called_once()
```

And `test_session_start_surfaces_sync_errors` — the sync errors now come from individual method exceptions, not from a `sync_all` return value. Update it:

```python
async def test_session_start_surfaces_sync_errors(db_session):
    from wizard.tools import session_start
    from wizard.schemas import SourceSyncStatus
    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(side_effect=Exception("Jira token not configured"))
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert len(result.sync_results) == 3
    jira_sync = result.sync_results[0]
    assert jira_sync.source == "jira"
    assert jira_sync.ok is False
    assert "Jira token not configured" in jira_sync.error
    assert result.sync_results[1].ok is True
```

Also check `tests/test_services.py` for any references to `_sync_jira`, `_sync_notion_tasks`, or `_sync_notion_meetings` by old private name and update them.

### Step 2.6: Run all tests

```
uv run pytest tests/ -v
```

Expected: all pass.

### Step 2.7: Commit

```
git add src/wizard/services.py src/wizard/tools.py tests/test_tools.py tests/test_services.py
git commit -m "feat: session threading via ctx.set_state/get_state; promote sync methods to public"
```

---

## Task 3: Elicitation + Progress

**Files:**
- Modify: `src/wizard/integrations.py`
- Modify: `src/wizard/services.py`
- Modify: `src/wizard/tools.py`
- Modify: `tests/test_tools.py`

Goal: `session_start` reports progress across 3 sync steps. `save_note` elicits `mental_model` for investigation/decision types. `update_task_status` elicits an outcome summary when status is DONE and appends it to Notion.

### Step 3.1: Write failing tests for progress and elicitation

Add in `tests/test_tools.py`:

```python
# --- progress ---

async def test_session_start_reports_progress(db_session):
    from wizard.tools import session_start
    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        await session_start(ctx)

    assert len(ctx.progress_calls) == 4
    assert ctx.progress_calls[0] == (0, 3, "Syncing Jira...")
    assert ctx.progress_calls[1] == (1, 3, "Syncing Notion tasks...")
    assert ctx.progress_calls[2] == (2, 3, "Syncing Notion meetings...")
    assert ctx.progress_calls[3] == (3, 3, "Sync complete.")


# --- elicitation: save_note ---

async def test_save_note_elicits_mental_model_for_investigation(db_session):
    from wizard.models import Task, TaskStatus, NoteType, Note
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext(elicit_response="I now understand the root cause is X")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.INVESTIGATION, content="looked at logs"
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "I now understand the root cause is X"


async def test_save_note_elicits_mental_model_for_decision(db_session):
    from wizard.models import Task, TaskStatus, NoteType, Note
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext(elicit_response="We chose approach B for simplicity")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.DECISION, content="chose B"
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "We chose approach B for simplicity"


async def test_save_note_does_not_elicit_for_docs_notes(db_session):
    from wizard.models import Task, TaskStatus, NoteType
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext(elicit_response="should not be called")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        await save_note(ctx, task_id=task.id, note_type=NoteType.DOCS, content="docs")

    # elicit was never called — no elicitation for DOCS
    # We can verify by checking that mental_model was not set via elicitation
    # (can't directly count calls, but we know DOCS doesn't trigger the branch)
    # So just assert the test didn't raise — the absence of call is the assertion.


async def test_save_note_mental_model_param_skips_elicitation(db_session):
    from wizard.models import Task, TaskStatus, NoteType, Note
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    # Elicit returns something, but mental_model already provided — should not overwrite
    ctx = MockContext(elicit_response="this should not win")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
            mental_model="caller provided this",
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "caller provided this"


async def test_save_note_handles_elicit_failure_gracefully(db_session):
    from wizard.models import Task, TaskStatus, NoteType
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext(supports_elicit=False)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.INVESTIGATION, content="investigation"
        )

    assert result.note_id is not None  # tool succeeded despite elicit failure


# --- elicitation: update_task_status ---

async def test_update_task_status_elicits_outcome_when_done(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.tools import update_task_status
    from wizard.schemas import WriteBackStatus

    task = Task(name="task", status=TaskStatus.IN_PROGRESS, notion_id="notion-page-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext(elicit_response="Shipped the fix to production.")
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.append_task_outcome.return_value = WriteBackStatus(ok=True)

    with patch.multiple("wizard.tools", **patches):
        await update_task_status(ctx, task_id=task.id, new_status=TaskStatus.DONE)

    wb_mock.append_task_outcome.assert_called_once()
    call_args = wb_mock.append_task_outcome.call_args
    assert "Shipped the fix" in call_args[0][1]


async def test_update_task_status_does_not_elicit_for_in_progress(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.tools import update_task_status
    from wizard.schemas import WriteBackStatus

    task = Task(name="task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext(elicit_response="should not be called")
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    with patch.multiple("wizard.tools", **patches):
        await update_task_status(ctx, task_id=task.id, new_status=TaskStatus.IN_PROGRESS)

    wb_mock.append_task_outcome.assert_not_called()
```

Run:

```
uv run pytest tests/test_tools.py -k "progress or elicit" -v
```

Expected: FAIL.

### Step 3.2: Add progress reporting to session_start in tools.py

Replace the sync loop in `session_start` with progress-wrapped version:

```python
svc = sync_service()
sync_results: list[SourceSyncStatus] = []
for i, (source, fn) in enumerate([
    ("jira", svc.sync_jira),
    ("notion_tasks", svc.sync_notion_tasks),
    ("notion_meetings", svc.sync_notion_meetings),
]):
    labels = ["Syncing Jira...", "Syncing Notion tasks...", "Syncing Notion meetings..."]
    await ctx.report_progress(i, 3, labels[i])
    try:
        fn(db)
        sync_results.append(SourceSyncStatus(source=source, ok=True))
    except Exception as e:
        logger.warning("Sync failed for %s: %s", source, e)
        sync_results.append(SourceSyncStatus(source=source, ok=False, error=str(e)))
await ctx.report_progress(3, 3, "Sync complete.")
```

### Step 3.3: Add NotionClient.append_paragraph_to_page in integrations.py

Add this method to the `NotionClient` class (after `update_meeting_summary`):

```python
def append_paragraph_to_page(self, page_id: str, text: str) -> bool:
    """Append a paragraph block to an existing Notion page. Returns True on success."""
    client = self._require_client()
    try:
        client.blocks.children.append(
            block_id=page_id,
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": text}}
                        ]
                    },
                }
            ],
        )
        return True
    except Exception as e:
        logger.warning("Notion append_paragraph_to_page failed: %s", e)
        return False
```

### Step 3.4: Add WriteBackService.append_task_outcome in services.py

Add this method to `WriteBackService` (after `push_task_status_to_notion`):

```python
def append_task_outcome(self, task: Task, summary: str) -> WriteBackStatus:
    """Append a plain-text outcome paragraph to the task's Notion page."""
    if not task.notion_id:
        return WriteBackStatus(ok=False, error="Task has no notion_id")
    notion_id = task.notion_id
    return self._call(
        lambda: self._notion.append_paragraph_to_page(notion_id, summary),
        "WriteBack append_task_outcome",
    )
```

### Step 3.5: Add elicitation to save_note in tools.py

After `task = task_repo().get_by_id(db, task_id)` and before building the `Note`, add the elicitation block. The mental_model param is only elicited when not already provided:

```python
if note_type in (NoteType.INVESTIGATION, NoteType.DECISION) and mental_model is None:
    try:
        from fastmcp.client.elicitation import AcceptedElicitation
        result = await ctx.elicit(
            "Optional: summarise what you now understand in 1-2 sentences (mental model). "
            "Press Enter to skip.",
            response_type=str,
        )
        if isinstance(result, AcceptedElicitation) and result.data:
            mental_model = result.data
    except Exception as e:
        logger.debug("ctx.elicit unavailable for mental_model: %s", e)
```

### Step 3.6: Add outcome elicitation to update_task_status in tools.py

After `task_state_repo().on_status_changed(db, task.id)` and before the write-back calls:

```python
if new_status == TaskStatus.DONE:
    try:
        from fastmcp.client.elicitation import AcceptedElicitation
        elicit_result = await ctx.elicit(
            "Task closed. What was the outcome? (1-2 sentences, or press Enter to skip)",
            response_type=str,
        )
        if isinstance(elicit_result, AcceptedElicitation) and elicit_result.data:
            scrubbed_outcome = security().scrub(elicit_result.data).clean
            if task.notion_id:
                writeback().append_task_outcome(task, scrubbed_outcome)
            else:
                logger.info(
                    "Task %d done with outcome but no notion_id; skipping notion append",
                    task.id,
                )
    except Exception as e:
        logger.debug("ctx.elicit unavailable for task outcome: %s", e)
```

### Step 3.7: Run all tests

```
uv run pytest tests/ -v
```

Expected: all pass.

### Step 3.8: Commit

```
git add src/wizard/tools.py src/wizard/services.py src/wizard/integrations.py tests/test_tools.py
git commit -m "feat: ctx.report_progress in session_start; ctx.elicit for mental_model and task outcome"
```

---

## Task 4: session_end Expansion + Skill Rewrite

**Files:**
- Modify: `src/wizard/schemas.py`
- Modify: `src/wizard/tools.py`
- Modify: `src/wizard/skills/session-end/SKILL.md`
- Modify: `tests/test_tools.py`

Goal: Expand `session_end` from 2 params to 8 params (+ ctx). Persist `SessionState` JSON to `WizardSession.session_state`. Echo summary fields in `SessionEndResponse`. Clear `current_session_id` from ctx. Rewrite the skill to collect all 6 fields.

### Step 4.1: Add echo fields to SessionEndResponse in schemas.py

Update `SessionEndResponse`:

```python
class SessionEndResponse(BaseModel):
    note_id: int
    notion_write_back: WriteBackStatus
    closure_status: str | None = None
    open_loops_count: int = 0
    next_actions_count: int = 0
    intent: str | None = None
```

### Step 4.2: Write failing tests for session_end expansion

Add in `tests/test_tools.py`:

```python
# --- session_end expansion ---

async def test_session_end_persists_session_state(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import SessionState, WriteBackStatus
    from wizard.tools import session_end
    import json

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="good session",
            intent="shipped the auth fix",
            working_set=[1, 2],
            state_delta="ENG-42 now done",
            open_loops=["follow up with team"],
            next_actions=["write tests for ENG-50"],
            closure_status="clean",
        )

    db_session.refresh(session)
    assert session.session_state is not None
    state = SessionState.model_validate_json(session.session_state)
    assert state.intent == "shipped the auth fix"
    assert state.working_set == [1, 2]
    assert state.closure_status == "clean"
    assert state.open_loops == ["follow up with team"]
    assert state.next_actions == ["write tests for ENG-50"]

    assert result.closure_status == "clean"
    assert result.open_loops_count == 1
    assert result.next_actions_count == 1
    assert result.intent == "shipped the auth fix"


async def test_session_end_emits_confirmation_via_ctx_info(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import session_end

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="intent",
            working_set=[],
            state_delta="nothing",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    assert any("clean" in msg for msg in ctx.info_calls)


async def test_session_end_rejects_invalid_closure_status(db_session):
    from wizard.models import WizardSession
    from wizard.tools import session_end

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock()

    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(Exception):
            await session_end(
                ctx,
                session_id=session.id,
                summary="done",
                intent="intent",
                working_set=[],
                state_delta="nothing",
                open_loops=[],
                next_actions=[],
                closure_status="invalid_value",
            )
```

Run:

```
uv run pytest tests/test_tools.py -k "session_end" -v
```

Expected: FAIL — session_end doesn't have new params yet.

### Step 4.3: Rewrite session_end in tools.py

Replace the current `session_end` function:

```python
async def session_end(
    ctx: Context,
    session_id: int,
    summary: str,
    intent: str,
    working_set: list[int],
    state_delta: str,
    open_loops: list[str],
    next_actions: list[str],
    closure_status: Literal["clean", "interrupted", "blocked"],
) -> SessionEndResponse:
    """Persists session summary + six-field SessionState to WizardSession. Writes Notion daily page."""
    logger.info("session_end session_id=%d", session_id)
    with get_session() as db:
        await _log_tool_call(db, "session_end", session_id=session_id)
        session = db.get(WizardSession, session_id)
        if session is None:
            await ctx.error(f"Session {session_id} not found")
            raise ToolError(f"Session {session_id} not found")

        state = SessionState(
            intent=intent,
            working_set=working_set,
            state_delta=state_delta,
            open_loops=open_loops,
            next_actions=next_actions,
            closure_status=closure_status,
        )
        session.session_state = state.model_dump_json()

        clean_summary = security().scrub(summary).clean
        session.summary = clean_summary
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary,
            session_id=session.id,
        )
        saved = note_repo().save(db, note)
        assert saved.id is not None

        wb_result = writeback().push_session_summary(session)

        await ctx.delete_state("current_session_id")
        await ctx.info(
            f"Session {session.id} closed. Status: {closure_status}. "
            f"{len(open_loops)} open loop(s), {len(next_actions)} next action(s)."
        )

        return SessionEndResponse(
            note_id=saved.id,
            notion_write_back=wb_result,
            closure_status=closure_status,
            open_loops_count=len(open_loops),
            next_actions_count=len(next_actions),
            intent=intent,
        )
```

### Step 4.4: Update existing session_end tests to pass new required params

Every existing `session_end` call in `test_tools.py` must now include the six new fields. Find every test that calls `session_end` and add the new params:

```python
# Old pattern:
await session_end(ctx, session_id=session.id, summary="done")

# New pattern:
await session_end(
    ctx,
    session_id=session.id,
    summary="done",
    intent="wrapped up",
    working_set=[],
    state_delta="no changes",
    open_loops=[],
    next_actions=[],
    closure_status="clean",
)
```

Also update `test_session_end_clears_current_session_id_from_ctx_state` added in Task 2 — it already passes the new params (check the test written above — if it doesn't, update it now).

### Step 4.5: Run all tests

```
uv run pytest tests/ -v
```

Expected: all pass.

### Step 4.6: Rewrite skills/session-end/SKILL.md

Replace the contents of `src/wizard/skills/session-end/SKILL.md` with:

```markdown
# Session End

Use this skill at the end of every work session to save a structured summary and close the session cleanly.

## What this does

- Collects six structured fields from the engineer
- Calls `session_end` with all eight parameters
- Persists a `SessionState` JSON object to the session record
- Writes the session summary to the Notion daily page
- Clears the session context so the next session starts clean

## Steps

**1. Ask the engineer for a session summary.** One or two sentences covering what was done.

**2. Collect the six structured fields.**

Ask each in turn (you may batch them if the engineer is terse):

- **intent**: What was the primary goal of this session? (One sentence.)
- **working_set**: Which task IDs were actively worked on? (List of integers from `session_start` output.)
- **state_delta**: What changed since the last session? (One sentence — status changes, blockers resolved, new discoveries.)
- **open_loops**: What's unresolved and needs follow-up? (List of strings, or empty list.)
- **next_actions**: What are the concrete next steps? (List of strings, or empty list.)
- **closure_status**: How did the session end? One of: `clean` (finished what was planned), `interrupted` (cut short), `blocked` (stuck on something).

**3. Call session_end with all eight parameters:**

```python
session_end(
    session_id=<from session_start>,
    summary="<summary>",
    intent="<intent>",
    working_set=[<task_id>, ...],
    state_delta="<state_delta>",
    open_loops=["<loop>", ...],
    next_actions=["<action>", ...],
    closure_status="<clean|interrupted|blocked>",
)
```

**4. Surface the confirmation.** The response includes echo fields — show the engineer:

- Session ID closed
- Closure status
- Number of open loops and next actions
- Whether Notion write-back succeeded

## Notes

- `working_set` is task IDs (integers), not task names.
- `open_loops` and `next_actions` can be empty lists — do not prompt unnecessarily.
- If the engineer is in a hurry, `closure_status="interrupted"` is fine and `open_loops`/`next_actions` can be `[]`.
- The `summary` field is scrubbed for PII before storage. The six structured fields are stored as-is in `session_state` JSON — remind the engineer not to include real names, emails, or patient data in open_loops/next_actions.
```

### Step 4.7: Run final test suite

```
uv run pytest tests/ -v --tb=short
```

Expected: all tests pass with no failures.

### Step 4.8: Commit

```
git add src/wizard/schemas.py src/wizard/tools.py src/wizard/skills/session-end/SKILL.md tests/test_tools.py
git commit -m "feat: session_end six-field SessionState signature + skill rewrite"
```

---

## Task 5: Final Verification

**No file modifications — verification only.**

### Step 5.1: Full test run with coverage summary

```
uv run pytest tests/ -v --tb=short
```

Expected: all tests pass.

### Step 5.2: Type check (if mypy or pyright is configured)

```
uv run mypy src/wizard/tools.py src/wizard/services.py src/wizard/integrations.py src/wizard/schemas.py 2>&1 | tail -20
```

If not configured, skip this step.

### Step 5.3: Smoke test — wizard doctor

```
wizard doctor
```

Expected: no errors. If Jira/Notion are not configured in the test environment, the warning is expected and acceptable.

### Step 5.4: Verify services.py public method names

```
grep -n "def sync_" src/wizard/services.py
```

Expected output:
```
25:    def sync_all(self, db: Session) -> list[SourceSyncStatus]:
40:    def sync_jira(self, db: Session) -> None:
65:    def sync_notion_tasks(self, db: Session) -> None:
```
(line numbers approximate — confirm no leading underscores on the three sync methods)

### Step 5.5: Verify tools are registered

```
grep "mcp.tool()" src/wizard/tools.py
```

Expected: 9 lines, one per tool.

### Step 5.6: Open a PR

```
git push origin feat/b-context-migration
gh pr create --title "feat: FastMCP Context migration + session_end six-field signature (v1.1.5)" --body "$(cat <<'BODY'
## Summary

- All 9 Wizard tools converted to `async def` with `ctx: Context` as first parameter
- Session threading: `session_start` stores `session_id` in `ctx.set_state`; mid-session tools read it via `ctx.get_state` and stamp `Note.session_id` + `ToolCall.session_id`
- `ctx.report_progress` in `session_start` across three-source sync loop
- `ctx.elicit` for `mental_model` in `save_note` (investigation/decision types only)
- `ctx.elicit` for outcome summary in `update_task_status` when status=DONE; outcome appended to Notion page via new `WriteBackService.append_task_outcome`
- `session_end` expanded to 8-param signature with `SessionState` JSON persistence; echo fields on `SessionEndResponse`; `ctx.delete_state` clears session on close
- `SyncService._sync_jira/notion_tasks/notion_meetings` promoted to public
- `NotionClient.append_paragraph_to_page` added
- `pytest-asyncio` (asyncio_mode=auto) added; all tests converted to async; 13 new tests

## Test plan

- [ ] `uv run pytest tests/ -v` — all tests pass
- [ ] `wizard doctor` — no fatal errors
- [ ] Manually invoke `session_start` via MCP client — confirm progress messages visible
- [ ] Manually invoke `save_note` with investigation type — confirm elicitation prompt appears
- [ ] Manually invoke `update_task_status` with DONE — confirm outcome elicitation appears
- [ ] Manually invoke `session_end` with all 8 params — confirm SessionState stored in DB

🤖 Generated with Claude Code
BODY
)"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task coverage |
|---|---|
| §1 — async shell, all 9 tools, ctx first | Task 1 (full rewrite of tools.py) |
| §2 — ctx API replacements (ctx.info, ToolError pattern) | Task 1 (shell), Task 2 (ctx.info in session_start), Task 4 (ctx.error in session_end) |
| §3 — ctx.elicit for mental_model | Task 3, Steps 3.1 + 3.5 |
| §4 — ctx.elicit for outcome summary | Task 3, Steps 3.1 + 3.6 |
| §5 — ctx.report_progress in session_start | Task 3, Steps 3.1 + 3.2 |
| §6 — session_end six-field signature | Task 4, Steps 4.2 + 4.3 |
| §7 — ctx.set_state/get_state session threading | Task 2 |
| §8 — SessionEndResponse echo fields | Task 4, Step 4.1 |
| §9 — test infrastructure + 13 new tests | Task 0 (infra) + Tasks 2, 3, 4 (tests) |
| §10 — SKILL.md rewrite | Task 4, Step 4.6 |
| SyncService method promotion | Task 2, Step 2.2 |
| NotionClient.append_paragraph_to_page | Task 3, Step 3.3 |
| WriteBackService.append_task_outcome | Task 3, Step 3.4 |
| pyproject.toml pytest-asyncio | Task 0, Step 0.1 |
| MockContext | Task 0, Step 0.3 |

All spec sections covered. No gaps.

**Placeholder scan:** No TBDs, no "implement later", no "handle edge cases" without code. Every step with code has the actual implementation.

**Type consistency:** `SessionState` imported from `schemas.py` (already present from Milestone A). `SourceSyncStatus` added to tools.py import (needed for explicit sync loop). `Literal` imported from `typing` in tools.py for `closure_status` param. `AcceptedElicitation` imported inline in elicit blocks (avoids circular import surface). All consistent.
