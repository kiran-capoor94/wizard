# Codebase Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify wizard MCP server implementation — honest sync, deduplicated patterns, consistent logging — without changing the MCP contract.

**Architecture:** All 9 tools become sync. Integration clients get `_require_client()` to eliminate 10 guard blocks. WriteBackService gets `_call()` helper to eliminate duplicated try/except. Logging added to 7 files.

**Tech Stack:** Python 3.14, FastMCP, SQLModel, httpx, notion-client, pydantic

---

### Task 1: Async to Sync Conversion (tools.py + tests)

**Files:**
- Modify: `src/tools.py:1-359`
- Modify: `tests/test_tools.py:1-509`

- [ ] **Step 1: Remove async imports and ctx from tools.py**

Replace the imports block at the top of `src/tools.py` with:

```python
from fastmcp.exceptions import ToolError
from sqlmodel import select

from .database import get_session
from .deps import meeting_repo, note_repo, security, sync_service, task_repo, writeback
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
    TaskStartResponse,
    UpdateTaskStatusResponse,
)
```

Removed: `from fastmcp import Context`, `from fastmcp.server.dependencies import CurrentContext`.

- [ ] **Step 2: Convert session_start to sync**

Replace the `session_start` function (lines 40-62) with:

```python
def session_start() -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        sync_results = sync_service().sync_all(db)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
        )
```

- [ ] **Step 3: Convert session_end to sync**

Replace the `session_end` function (lines 219-250) with:

```python
def session_end(session_id: int, summary: str) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    with get_session() as db:
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
```

- [ ] **Step 4: Convert ingest_meeting to sync**

Replace the `ingest_meeting` function (lines 253-303) with:

```python
def ingest_meeting(
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    with get_session() as db:
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
```

- [ ] **Step 5: Convert create_task to sync**

Replace the `create_task` function (lines 306-344) with:

```python
def create_task(
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    with get_session() as db:
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
```

- [ ] **Step 6: Update tests — remove asyncio.run and mock context**

In `tests/test_tools.py`, replace the imports (lines 1-2) with:

```python
from unittest.mock import MagicMock, patch
```

Remove the `_mock_context` helper (lines 9-15) entirely.

Update every test that used `asyncio.run()` or `ctx=_mock_context()`:

**test_session_start_creates_session** — replace `asyncio.run(session_start(ctx=_mock_context()))` with `session_start()`

**test_session_start_calls_sync** — replace `asyncio.run(session_start(ctx=_mock_context()))` with `session_start()`

**test_session_start_surfaces_sync_errors** — replace `asyncio.run(session_start(ctx=_mock_context()))` with `session_start()`

**test_session_end_saves_summary_note** — replace `asyncio.run(session_end(session_id=session_id, summary="wrapped up today's work", ctx=_mock_context()))` with `session_end(session_id=session_id, summary="wrapped up today's work")`

**test_ingest_meeting_creates_meeting** — replace `asyncio.run(ingest_meeting(title="Sprint Planning", content="john@example.com reported a bug", source_id="krisp-abc", source_url="https://krisp.ai/m/abc", category=MeetingCategory.PLANNING, ctx=_mock_context()))` with `ingest_meeting(title="Sprint Planning", content="john@example.com reported a bug", source_id="krisp-abc", source_url="https://krisp.ai/m/abc", category=MeetingCategory.PLANNING)`

**test_ingest_meeting_dedup_by_source_id** — replace `asyncio.run(ingest_meeting(title="New", content="new", source_id="krisp-abc", ctx=_mock_context()))` with `ingest_meeting(title="New", content="new", source_id="krisp-abc")`

**test_create_task_creates_and_links** — replace `asyncio.run(create_task(name="Fix john@example.com auth bug", priority=TaskPriority.HIGH, meeting_id=meeting_id, ctx=_mock_context()))` with `create_task(name="Fix john@example.com auth bug", priority=TaskPriority.HIGH, meeting_id=meeting_id)`

**test_compounding_loop_across_two_sessions** — replace all `asyncio.run(session_start(ctx=_mock_context()))` with `session_start()`, and `asyncio.run(session_end(session_id=session_id, summary="Investigated auth bug", ctx=_mock_context()))` with `session_end(session_id=session_id, summary="Investigated auth bug")`

- [ ] **Step 7: Run tests to verify**

Run: `pytest tests/test_tools.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```
git add src/tools.py tests/test_tools.py
git commit -m "refactor: convert all tools to sync, drop async/ctx ceremony"
```

---

### Task 2: Fail-Fast Client Init (integrations.py)

**Files:**
- Modify: `src/integrations.py:31-300`

- [ ] **Step 1: Add _require_client to JiraClient**

In `src/integrations.py`, add after the `close()` method (after line 51):

```python
    def _require_client(self) -> httpx.Client:
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        return self._client
```

- [ ] **Step 2: Replace guards in JiraClient methods**

In `fetch_open_tasks`, replace lines 53-54:
```python
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
```
with:
```python
        client = self._require_client()
```
Then replace `self._client.get` (line 57) with `client.get`.

In `update_task_status`, replace lines 78-79 the same way. Then replace `self._client.post` (line 81) with `client.post`.

- [ ] **Step 3: Add _require_client to NotionClient**

Add after `__init__` (after line 112):

```python
    def _require_client(self) -> NotionSdkClient:
        if self._client is None:
            raise ConfigurationError("Notion token not configured")
        return self._client
```

- [ ] **Step 4: Replace guards in NotionClient methods**

For each of these 8 methods, replace the `if self._client is None: raise ConfigurationError(...)` guard with `client = self._require_client()`, then use `client` instead of `self._client` in the method body:

- `_query_database` (line 116-117) — replace `self._client.request` with `client.request`
- `fetch_tasks` (line 126-127) — only replace the guard (this method calls `_query_database` via `collect_paginated_api`)
- `fetch_meetings` (line 158-159) — same as `fetch_tasks`
- `create_task_page` (line 199-200) — replace `self._client.pages.create` with `client.pages.create`
- `create_meeting_page` (line 232-233) — replace `self._client.pages.create` with `client.pages.create`
- `update_task_status` (line 257-258) — replace `self._client.pages.update` with `client.pages.update`
- `update_meeting_summary` (line 272-273) — replace `self._client.pages.update` with `client.pages.update`
- `update_daily_page` (line 287-288) — replace `self._client.pages.update` with `client.pages.update`

- [ ] **Step 5: Run tests to verify**

Run: `pytest tests/test_integrations.py -v`
Expected: All tests PASS (behavior identical — same ConfigurationError raised)

- [ ] **Step 6: Commit**

```
git add src/integrations.py
git commit -m "refactor: _require_client() replaces 10 inline None guards"
```

---

### Task 3: NoteDetail.from_model() classmethod

**Files:**
- Modify: `src/schemas.py:158-165`
- Modify: `src/tools.py` (in `task_start`)
- Modify: `src/resources.py:57-67`

- [ ] **Step 1: Add from_model classmethod to NoteDetail**

In `src/schemas.py`, add to the `NoteDetail` class (after the `source_id` field, before the blank line):

```python
    @classmethod
    def from_model(cls, note) -> "NoteDetail":
        assert note.id is not None
        return cls(
            id=note.id,
            note_type=note.note_type,
            content=note.content,
            created_at=note.created_at,
            source_id=note.source_id,
        )
```

- [ ] **Step 2: Replace conversion in tools.py task_start**

In `src/tools.py`, replace the note conversion block in `task_start`:

```python
            prior_notes: list[NoteDetail] = []
            for n in notes:
                assert n.id is not None
                prior_notes.append(
                    NoteDetail(
                        id=n.id,
                        note_type=n.note_type,
                        content=n.content,
                        created_at=n.created_at,
                        source_id=n.source_id,
                    )
                )
```

with:

```python
            prior_notes = [NoteDetail.from_model(n) for n in notes]
```

- [ ] **Step 3: Replace conversion in resources.py task_context**

In `src/resources.py`, replace:

```python
        note_details = [
            NoteDetail(
                id=n.id,
                note_type=n.note_type,
                content=n.content,
                created_at=n.created_at,
                source_id=n.source_id,
            )
            for n in notes
            if n.id is not None
        ]
        return TaskContextResource(task=task_ctx, notes=note_details)
```

with:

```python
        note_details = [NoteDetail.from_model(n) for n in notes if n.id is not None]
        return TaskContextResource(task=task_ctx, notes=note_details)
```

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/test_tools.py tests/test_resources.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```
git add src/schemas.py src/tools.py src/resources.py
git commit -m "refactor: NoteDetail.from_model() replaces 2 duplicated conversions"
```

---

### Task 4: WriteBackService._call() helper

**Files:**
- Modify: `src/services.py:188-315`

- [ ] **Step 1: Add _call helper to WriteBackService**

In `src/services.py`, add after `WriteBackService.__init__` (after line 191):

```python
    def _call(self, fn, error_label: str, **status_kwargs) -> WriteBackStatus:
        try:
            result = fn()
            if result:
                return WriteBackStatus(ok=True, **status_kwargs)
            return WriteBackStatus(ok=False, error=f"{error_label} failed")
        except Exception as e:
            logger.warning("%s failed: %s", error_label, e)
            return WriteBackStatus(ok=False, error=str(e))
```

- [ ] **Step 2: Simplify push_task_status**

Replace `push_task_status` (lines 193-204) with:

```python
    def push_task_status(self, task: Task) -> WriteBackStatus:
        if not task.source_id:
            return WriteBackStatus(ok=False, error="Task has no Jira source_id")
        jira_status = StatusMapper.local_to_jira(task.status)
        return self._call(
            lambda: self._jira.update_task_status(task.source_id, jira_status),
            "WriteBack push_task_status (Jira)",
        )
```

- [ ] **Step 3: Simplify push_task_status_to_notion**

Replace `push_task_status_to_notion` (lines 206-217) with:

```python
    def push_task_status_to_notion(self, task: Task) -> WriteBackStatus:
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        notion_status = StatusMapper.local_to_notion(task.status)
        return self._call(
            lambda: self._notion.update_task_status(task.notion_id, notion_status),
            "WriteBack push_task_status (Notion)",
        )
```

- [ ] **Step 4: Simplify push_meeting_to_notion (update path only)**

Replace `push_meeting_to_notion` (lines 246-287) with:

```python
    def push_meeting_to_notion(self, meeting: Meeting) -> WriteBackStatus:
        """Create or update meeting in Notion. Returns page_id in WriteBackStatus on success."""
        if meeting.notion_id:
            if not meeting.summary:
                return WriteBackStatus(ok=True, page_id=meeting.notion_id)
            return self._call(
                lambda: self._notion.update_meeting_summary(
                    meeting.notion_id, meeting.summary
                ),
                "WriteBack push_meeting_to_notion (update)",
                page_id=meeting.notion_id,
            )
        notion_category = MeetingCategoryMapper.local_to_notion(meeting.category)
        if not notion_category:
            return WriteBackStatus(
                ok=False,
                error=f"No Notion category mapping for '{meeting.category.value}'",
            )
        try:
            page_id = self._notion.create_meeting_page(
                title=meeting.title,
                category=notion_category,
                krisp_url=(
                    meeting.source_url if meeting.source_type == "KRISP" else None
                ),
                summary=meeting.summary,
            )
            if page_id:
                return WriteBackStatus(ok=True, page_id=page_id)
            return WriteBackStatus(
                ok=False, error="Notion create_meeting_page returned no page ID"
            )
        except Exception as e:
            logger.warning("WriteBack push_meeting_to_notion (create) failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))
```

- [ ] **Step 5: Simplify push_meeting_summary**

Replace `push_meeting_summary` (lines 289-303) with:

```python
    def push_meeting_summary(self, meeting: Meeting) -> WriteBackStatus:
        if not meeting.notion_id:
            return WriteBackStatus(ok=False, error="Meeting has no notion_id")
        if not meeting.summary:
            return WriteBackStatus(ok=False, error="Meeting has no summary")
        return self._call(
            lambda: self._notion.update_meeting_summary(
                meeting.notion_id, meeting.summary
            ),
            "WriteBack push_meeting_summary",
        )
```

- [ ] **Step 6: Simplify push_session_summary**

Replace `push_session_summary` (lines 305-315) with:

```python
    def push_session_summary(self, session: WizardSession) -> WriteBackStatus:
        if not session.summary:
            return WriteBackStatus(ok=False, error="Session has no summary")
        return self._call(
            lambda: self._notion.update_daily_page(session.summary),
            "WriteBack push_session_summary",
        )
```

Note: `push_task_to_notion` stays as-is — its create path returns a `page_id` string that doesn't fit the `_call` pattern cleanly.

- [ ] **Step 7: Run tests to verify**

Run: `pytest tests/test_services.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```
git add src/services.py
git commit -m "refactor: WriteBackService._call() deduplicates try/except/log pattern"
```

---

### Task 5: Extract _extract_krisp_id helper

**Files:**
- Modify: `src/integrations.py` (add helper after `_extract_jira_key`)
- Modify: `src/services.py:131-139`
- Modify: `tests/test_integrations.py`

- [ ] **Step 1: Write test for _extract_krisp_id**

Add to `tests/test_integrations.py` after the existing `test_extract_jira_key_from_url`:

```python
def test_extract_krisp_id_from_url():
    """_extract_krisp_id should extract last path segment from Krisp URL"""
    from src.integrations import _extract_krisp_id

    assert _extract_krisp_id("https://krisp.ai/m/abc123") == "abc123"
    assert _extract_krisp_id("https://krisp.ai/m/abc123/") == "abc123"
    assert _extract_krisp_id("https://krisp.ai/m/abc123?foo=bar") == "abc123"
    assert _extract_krisp_id(None) is None
    assert _extract_krisp_id("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integrations.py::test_extract_krisp_id_from_url -v`
Expected: FAIL — `ImportError: cannot import name '_extract_krisp_id'`

- [ ] **Step 3: Add _extract_krisp_id to integrations.py**

In `src/integrations.py`, add after `_extract_jira_key` (after line 97):

```python
def _extract_krisp_id(url: str | None) -> str | None:
    """Extract meeting ID from last path segment of a Krisp URL."""
    if not url:
        return None
    try:
        segment = url.rstrip("/").split("/")[-1].split("?")[0].strip()
        return segment or None
    except Exception:
        logger.warning("Failed to extract krisp_id from URL: %s", url)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_integrations.py::test_extract_krisp_id_from_url -v`
Expected: PASS

- [ ] **Step 5: Replace inline parsing in services.py**

In `src/services.py`, add `_extract_krisp_id` to the integrations import:

```python
from .integrations import JiraClient, NotionClient, _extract_krisp_id
```

Replace the inline krisp_id extraction in `_sync_notion_meetings` (lines 131-139):

```python
            # Extract krisp_id from krisp_url last path segment
            krisp_id = None
            if krisp_url:
                try:
                    segment = krisp_url.rstrip("/").split("/")[-1].split("?")[0].strip()
                    if segment:
                        krisp_id = segment
                except Exception:
                    pass
```

with:

```python
            krisp_id = _extract_krisp_id(krisp_url)
```

- [ ] **Step 6: Run tests to verify**

Run: `pytest tests/test_services.py tests/test_integrations.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```
git add src/integrations.py src/services.py tests/test_integrations.py
git commit -m "refactor: extract _extract_krisp_id, replace silent except pass"
```

---

### Task 6: Logging — infrastructure files

**Files:**
- Modify: `src/config.py`
- Modify: `src/database.py`
- Modify: `src/deps.py`
- Modify: `src/security.py`
- Modify: `src/repositories.py`

- [ ] **Step 1: Add logging to config.py**

Add `import logging` after existing imports and add logger:

```python
logger = logging.getLogger(__name__)
```

In `JsonConfigSettingsSource.__call__`, replace the method body:

```python
    def __call__(self) -> dict[str, Any]:
        config_file = os.environ.get(
            "WIZARD_CONFIG_FILE",
            str(Path.home() / ".wizard" / "config.json"),
        )
        try:
            with open(config_file) as f:
                data = json.load(f)
            logger.info("Loaded config from %s", config_file)
            return data
        except FileNotFoundError:
            logger.info("No config file at %s, using defaults", config_file)
            return {}
```

- [ ] **Step 2: Add logging to database.py**

Add after existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Add after engine creation (after line 18):

```python
logger.info("Database engine created: %s", settings.db)
```

- [ ] **Step 3: Add logging to deps.py**

Add after existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Add `logger.debug("Creating <ClassName> singleton")` as the first line of each of the 8 factory functions. Example for `jira_client`:

```python
@lru_cache
def jira_client() -> JiraClient:
    logger.debug("Creating JiraClient singleton")
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
    )
```

Apply the same pattern for: `notion_client` ("Creating NotionClient singleton"), `security` ("Creating SecurityService singleton"), `sync_service` ("Creating SyncService singleton"), `writeback` ("Creating WriteBackService singleton"), `task_repo` ("Creating TaskRepository singleton"), `meeting_repo` ("Creating MeetingRepository singleton"), `note_repo` ("Creating NoteRepository singleton").

- [ ] **Step 4: Add logging to security.py**

Add after existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

In the `scrub` method, add before the final return statement:

```python
        if original_to_stub:
            logger.info(
                "PII scrubbed: %d substitution(s) across patterns",
                len(original_to_stub),
            )
```

- [ ] **Step 5: Add logging to repositories.py**

Add after existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

In `TaskRepository.get_by_id`, add before the ValueError raise:

```python
            logger.warning("Task %d not found", task_id)
```

In `MeetingRepository.get_by_id`, add before the ValueError raise:

```python
            logger.warning("Meeting %d not found", meeting_id)
```

- [ ] **Step 6: Run all tests to verify**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```
git add src/config.py src/database.py src/deps.py src/security.py src/repositories.py
git commit -m "feat: add logging to config, database, deps, security, repositories"
```

---

### Task 7: Logging — tools.py

**Files:**
- Modify: `src/tools.py`

- [ ] **Step 1: Add logger to tools.py**

Add after existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Add entry logging to all 9 tools**

Add `logger.info(...)` as the first line inside each tool function:

- `session_start`: `logger.info("session_start")`
- `task_start`: `logger.info("task_start task_id=%d", task_id)`
- `save_note`: `logger.info("save_note task_id=%d note_type=%s", task_id, note_type.value)`
- `update_task_status`: `logger.info("update_task_status task_id=%d new_status=%s", task_id, new_status.value)`
- `get_meeting`: `logger.info("get_meeting meeting_id=%d", meeting_id)`
- `save_meeting_summary`: `logger.info("save_meeting_summary meeting_id=%d session_id=%d", meeting_id, session_id)`
- `session_end`: `logger.info("session_end session_id=%d", session_id)`
- `ingest_meeting`: `logger.info("ingest_meeting source_id=%s", source_id)`
- `create_task`: `logger.info("create_task priority=%s category=%s", priority.value, category.value)`

- [ ] **Step 3: Add failure logging to the 5 tools with try/except**

In each of these 5 tools, add `logger.warning(...)` before the `raise ToolError`:

- `task_start`: `logger.warning("task_start failed: %s", e)`
- `save_note`: `logger.warning("save_note failed: %s", e)`
- `update_task_status`: `logger.warning("update_task_status failed: %s", e)`
- `get_meeting`: `logger.warning("get_meeting failed: %s", e)`
- `save_meeting_summary`: `logger.warning("save_meeting_summary failed: %s", e)`

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/test_tools.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```
git add src/tools.py
git commit -m "feat: add logging to all tool functions"
```
