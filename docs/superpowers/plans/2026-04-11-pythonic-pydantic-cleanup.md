# Pythonic & Pydantic Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate non-Pythonic patterns across the wizard MCP server — replace dataclasses with Pydantic, modernize typing for Python 3.14, replace manual singletons with `@lru_cache`, enum-type tool params, and replace raw Notion dict traversal with Pydantic models.

**Architecture:** Internal refactoring only. No external interface changes (MCP tool names, resource URIs, prompt names, response schemas all stay identical). No database changes.

**Tech Stack:** Python 3.14, Pydantic v2, SQLModel, FastMCP 3.2+

---

### Task 1: Modern Typing + pyproject.toml

**Files:**
- Modify: `pyproject.toml:7`
- Modify: `src/models.py:2-3`
- Modify: `src/schemas.py:2`
- Modify: `src/repositories.py:1`
- Modify: `src/database.py:2`

- [ ] **Step 1: Bump requires-python in pyproject.toml**

```python
# Change line 7 from:
requires-python = ">=3.12"
# To:
requires-python = ">=3.14"
```

- [ ] **Step 2: Modernize models.py typing**

Replace:
```python
from typing import Optional
```

With nothing — remove the import entirely. Then replace all `Optional[X]` with `X | None` throughout the file. Affected fields:

```python
# Task
id: int | None = Field(default=None, primary_key=True)
due_date: datetime.datetime | None = None
notion_id: str | None = Field(default=None, index=True)
source_id: str | None = Field(...)
source_type: str | None = Field(default=None, index=True)
source_url: str | None = Field(default=None)

# Meeting
id: int | None = Field(default=None, primary_key=True)
notion_id: str | None = Field(default=None, index=True)
summary: str | None = None
source_id: str | None = Field(...)
source_type: str | None = Field(default=None, index=True)
source_url: str | None = Field(default=None)

# WizardSession
id: int | None = Field(default=None, primary_key=True)
summary: str | None = None

# Note
id: int | None = Field(default=None, primary_key=True)
source_id: str | None = Field(...)
source_type: str | None = Field(default=None, index=True)
session_id: int | None = Field(default=None, foreign_key="wizardsession.id")
source_url: str | None = Field(default=None)
task_id: int | None = Field(default=None, foreign_key="task.id")
meeting_id: int | None = Field(default=None, foreign_key="meeting.id")
session: WizardSession | None = Relationship(back_populates="notes")
```

- [ ] **Step 3: Modernize schemas.py typing**

Replace:
```python
from typing import Optional
```

With nothing. Replace all `Optional[X]` with `X | None` throughout the file. Affected fields in `TaskContext`, `MeetingContext`, `NoteDetail`, `SessionResource`, `SourceSyncStatus`, `WriteBackStatus`, `GetMeetingResponse`, `SessionEndResponse`, `IngestMeetingResponse`, `CreateTaskResponse`.

- [ ] **Step 4: Modernize repositories.py typing**

Replace:
```python
from typing import Optional
```

With nothing. Change `get_for_task` signature:
```python
def get_for_task(
    self,
    db: Session,
    task_id: int | None,
    source_id: str | None,
) -> list[Note]:
```

- [ ] **Step 5: Modernize database.py typing**

Replace:
```python
from typing import Generator
```

With `collections.abc.Generator`:
```python
from collections.abc import Generator
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass — these are pure type annotation changes.

- [ ] **Step 7: Commit**

```
git add pyproject.toml src/models.py src/schemas.py src/repositories.py src/database.py
git commit -m "refactor: modernize typing for Python 3.14

Replace Optional[X] with X | None, typing.Generator with
collections.abc.Generator. Bump requires-python to >=3.14."
```

---

### Task 2: ScrubResult dataclass to Pydantic BaseModel

**Files:**
- Modify: `src/security.py`
- Test: `tests/test_security.py` (no changes needed — existing tests verify behavior)

- [ ] **Step 1: Convert ScrubResult and modernize security.py**

Replace the full file content of `src/security.py`:

```python
import re

from pydantic import BaseModel


class ScrubResult(BaseModel):
    clean: str
    stubs_applied: dict[str, str]
    was_modified: bool


class SecurityService:
    PATTERNS: list[tuple[str, str, str]] = [
        ("NHS_ID", r"\b\d{3}\s\d{3}\s\d{4}\b", "NHS_ID"),
        ("NI_NUMBER", r"\b[A-Z]{2}\d{6}[A-D]\b", "NI_NUMBER"),
        ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "EMAIL"),
        ("PHONE", r"\b(\+44|0)[\d\s\-]{9,13}\b", "PHONE"),
        (
            "POSTCODE",
            r"\b([Gg][Ii][Rr]\s?0[Aa]{2}|[A-Za-z]{1,2}\d{1,2}[A-Za-z]?\s?\d[A-Za-z]{2})\b",
            "POSTCODE",
        ),
        ("SECRET", r"(Bearer\s[A-Za-z0-9\-._~+/]+=*|sk-[A-Za-z0-9]{20,})", "SECRET"),
    ]

    def __init__(self, allowlist: list[str] | None = None, enabled: bool = True):
        self._allowlist = allowlist or []
        self._allowlist_patterns = [re.compile(p) for p in self._allowlist]
        self._enabled = enabled

    def scrub(self, content: str) -> ScrubResult:
        if not self._enabled:
            return ScrubResult(clean=content, stubs_applied={}, was_modified=False)
        clean = content
        stubs_applied: dict[str, str] = {}
        counters: dict[str, int] = {}

        for _name, pattern, prefix in self.PATTERNS:

            def replace(m: re.Match, _prefix: str = prefix) -> str:
                matched = m.group(0)
                if any(p.search(matched) for p in self._allowlist_patterns):
                    return matched
                if matched in stubs_applied:
                    return stubs_applied[matched]
                counters[_prefix] = counters.get(_prefix, 0) + 1
                stub = f"[{_prefix}_{counters[_prefix]}]"
                stubs_applied[matched] = stub
                return stub

            clean = re.sub(pattern, replace, clean)

        return ScrubResult(
            clean=clean,
            stubs_applied=stubs_applied,
            was_modified=clean != content,
        )
```

- [ ] **Step 2: Run security tests**

Run: `pytest tests/test_security.py -v`
Expected: All 9 tests pass. `ScrubResult` is constructed by keyword args and accessed by attribute — BaseModel is a drop-in replacement.

- [ ] **Step 3: Commit**

```
git add src/security.py
git commit -m "refactor: ScrubResult dataclass to Pydantic BaseModel

Also modernize typing: Dict to dict, List to list, Tuple to tuple, Optional to | None."
```

---

### Task 3: Message dataclass to Pydantic BaseModel + prompts.py cleanup

**Files:**
- Modify: `src/prompts.py`
- Test: `tests/test_prompts.py` (no changes needed)

- [ ] **Step 1: Update prompts.py**

Replace the full file content:

```python
from pydantic import BaseModel

from .mcp_instance import mcp


class Message(BaseModel):
    """Lightweight prompt message.

    FastMCP accepts any object with ``role`` and ``content`` attributes.
    """

    role: str
    content: str


def session_triage(session_data: str) -> list[Message]:
    """Guides prioritisation after session_start."""
    return [
        Message(
            role="user",
            content=(
                "You just started a Wizard session. The data below contains your open tasks, "
                "blocked tasks, unsummarised meetings, and sync results.\n\n"
                "Triage priority:\n"
                "1. Check sync results for failures — if Jira or Notion failed to sync, note it and move on\n"
                "2. Blocked tasks first — identify what's blocking and whether you can unblock anything\n"
                "3. Unsummarised meetings — these need summaries before context is lost\n"
                "4. Open tasks by priority — high priority first, then medium, then low\n\n"
                "For each item, decide: act now, defer, or skip. Present your triage to the user "
                "and ask which item to start with."
            ),
        ),
        Message(
            role="user",
            content=f"Session data:\n\n{session_data}",
        ),
    ]


def task_investigation(task_data: str) -> list[Message]:
    """Directs Claude Code on how to work a task."""
    return [
        Message(
            role="user",
            content=(
                "You're starting work on a task. The data below contains the task details "
                "and all prior notes from previous sessions.\n\n"
                "Investigation guidelines:\n"
                "1. Read all prior notes first — understand what's already been done\n"
                "2. If compounding is true, build on existing investigation — don't repeat work\n"
                "3. If the task is code-related, use Serena to explore the codebase\n"
                "4. Record your findings as notes (investigation, decision, docs, learnings)\n"
                "5. If you need clarification from the user, ask — don't assume\n\n"
                "Your goal is to make progress on this task and leave clear notes for the next session."
            ),
        ),
        Message(
            role="user",
            content=f"Task data:\n\n{task_data}",
        ),
    ]


def meeting_summarisation(meeting_data: str) -> list[Message]:
    """Template for processing meeting transcripts."""
    return [
        Message(
            role="user",
            content=(
                "You're summarising a meeting. The data below contains the meeting transcript "
                "and any linked tasks.\n\n"
                "Summarisation template:\n"
                "1. Key decisions — what was decided and by whom\n"
                "2. Action items — concrete next steps with owners if mentioned\n"
                "3. Open questions — unresolved topics that need follow-up\n"
                "4. Relevant tasks — if any open tasks were discussed, note what was said\n\n"
                "Keep the summary concise but complete. Link to relevant tasks by ID if they "
                "were mentioned. The summary will be stored and written back to Notion."
            ),
        ),
        Message(
            role="user",
            content=f"Meeting data:\n\n{meeting_data}",
        ),
    ]


def session_wrapup() -> str:
    """Guides session end."""
    return (
        "You're ending a Wizard session. Before closing:\n\n"
        "1. Summarise what was accomplished this session\n"
        "2. List what's still open or in progress\n"
        "3. Note any status changes made to tasks\n"
        "4. Highlight anything that needs attention next session\n\n"
        "Keep it brief — this summary is for continuity between sessions. "
        "Focus on what changed and what matters next."
    )


def user_elicitation() -> str:
    """Meta-prompt: when and how to ask the user for direction."""
    return (
        "When working with Wizard session data, follow these rules for user interaction:\n\n"
        "Ask the user when:\n"
        "- Multiple tasks have similar priority and you need to choose which to work on\n"
        "- A blocked task's blocker is ambiguous and you need context\n"
        "- A meeting summary needs domain-specific interpretation\n"
        "- You're unsure whether to change a task's status\n"
        "- The triage order isn't obvious from priority alone\n\n"
        "Don't ask when:\n"
        "- There's one clear highest-priority item\n"
        "- The next step is obvious from prior notes\n"
        "- You're just recording findings as notes\n\n"
        "Prefer giving the user a concrete recommendation with your reasoning, "
        "then asking for confirmation, over open-ended questions."
    )


mcp.prompt()(session_triage)
mcp.prompt()(task_investigation)
mcp.prompt()(meeting_summarisation)
mcp.prompt()(session_wrapup)
mcp.prompt()(user_elicitation)
```

Changes from original:
- `dataclass` import replaced with `pydantic.BaseModel`
- `Message` extends `BaseModel` instead of `@dataclass`
- `_get_mcp()` wrapper replaced with direct `from .mcp_instance import mcp`
- `_mcp` variable replaced with direct `mcp` usage
- Docstring on `Message` simplified

- [ ] **Step 2: Run prompt tests**

Run: `pytest tests/test_prompts.py -v`
Expected: All 5 tests pass. Tests access `.content` and `.role` attributes — identical API.

- [ ] **Step 3: Commit**

```
git add src/prompts.py
git commit -m "refactor: Message dataclass to Pydantic BaseModel

Also replace _get_mcp() wrapper with direct import."
```

---

### Task 4: Mappers underscore prefix cleanup

**Files:**
- Modify: `src/mappers.py`
- Test: `tests/test_mappers.py` (no changes needed — tests use mapper classes, not dict names)

- [ ] **Step 1: Rename mapper dict constants**

In `src/mappers.py`, rename all 8 leading-underscore dicts and update references within mapper class methods:

```
_JIRA_STATUS_MAP                  -> JIRA_STATUS_MAP
_JIRA_PRIORITY_MAP                -> JIRA_PRIORITY_MAP
_NOTION_STATUS_MAP                -> NOTION_STATUS_MAP
_NOTION_PRIORITY_MAP              -> NOTION_PRIORITY_MAP
_LOCAL_TO_JIRA_STATUS             -> LOCAL_TO_JIRA_STATUS
_LOCAL_TO_NOTION_STATUS           -> LOCAL_TO_NOTION_STATUS
_NOTION_MEETING_CATEGORY_MAP      -> NOTION_MEETING_CATEGORY_MAP
_LOCAL_TO_NOTION_MEETING_CATEGORY -> LOCAL_TO_NOTION_MEETING_CATEGORY
```

Update every `.get(...)` reference within the mapper class staticmethods to use the new names.

- [ ] **Step 2: Run mapper tests**

Run: `pytest tests/test_mappers.py -v`
Expected: All 19 tests pass.

- [ ] **Step 3: Commit**

```
git add src/mappers.py
git commit -m "refactor: drop _ prefix from mapper lookup dicts

Module-level constants used by mapper classes, not private internals."
```

---

### Task 5: integrations.py + services.py import cleanup

**Files:**
- Modify: `src/integrations.py`
- Modify: `src/services.py`
- Test: `tests/test_integrations.py` (no changes needed yet)
- Test: `tests/test_services.py` (no changes needed)

- [ ] **Step 1: Clean up integrations.py imports**

Replace the top of `src/integrations.py`:

```python
# Before
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import httpx
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError
from notion_client.helpers import collect_paginated_api

if TYPE_CHECKING:
    from .schemas import JiraTaskData, NotionMeetingData, NotionTaskData

# After
import logging
import re

import httpx
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError
from notion_client.helpers import collect_paginated_api

from .schemas import JiraTaskData, NotionMeetingData, NotionTaskData
```

Also rename `_HTTPX_TIMEOUT` to `HTTPX_TIMEOUT` and update its one usage in `JiraClient.__init__`.

- [ ] **Step 2: Clean up services.py imports**

Replace the top of `src/services.py`:

```python
# Before
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from .integrations import JiraClient, NotionClient
from .mappers import MeetingCategoryMapper, PriorityMapper, StatusMapper
from .schemas import SourceSyncStatus, WriteBackStatus
from .security import SecurityService

if TYPE_CHECKING:
    from .models import Meeting, Task, WizardSession

# After
import datetime
import logging

from sqlmodel import Session, select

from .integrations import JiraClient, NotionClient
from .mappers import MeetingCategoryMapper, PriorityMapper, StatusMapper
from .models import Meeting, MeetingCategory, Task, WizardSession
from .schemas import SourceSyncStatus, WriteBackStatus
from .security import SecurityService
```

Then remove all in-function imports from `services.py` method bodies:
- `_sync_jira`: remove `from .models import Task`
- `_sync_notion_tasks`: remove `from .models import Task` and `import datetime as _dt`, replace `_dt.datetime` with `datetime.datetime`
- `_sync_notion_meetings`: remove `from .models import Meeting, MeetingCategory`

- [ ] **Step 3: Run integration and service tests**

Run: `pytest tests/test_integrations.py tests/test_services.py -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```
git add src/integrations.py src/services.py
git commit -m "refactor: drop __future__/TYPE_CHECKING, top-level imports

integrations.py: rename _HTTPX_TIMEOUT to HTTPX_TIMEOUT, direct schema imports.
services.py: direct model imports, move datetime to top-level."
```

---

### Task 6: Notion Property Pydantic Models

**Files:**
- Modify: `src/schemas.py` (add Notion property models)
- Modify: `src/integrations.py` (replace `_get_*` helpers with model usage)
- Modify: `tests/test_integrations.py` (rewrite helper function tests)

- [ ] **Step 1: Write failing tests for Notion property models**

Add to the top of `tests/test_integrations.py`, before the existing helper tests:

```python
from src.schemas import (
    NotionTitle, NotionRichText, NotionSelect, NotionMultiSelect,
    NotionUrl, NotionDate, NotionStatus,
)


class TestNotionTitle:
    def test_extracts_plain_text(self):
        prop = {"title": [{"plain_text": "Test Title"}]}
        assert NotionTitle.model_validate(prop).text == "Test Title"

    def test_returns_none_for_empty(self):
        assert NotionTitle.model_validate({"title": []}).text is None

    def test_returns_none_for_missing(self):
        assert NotionTitle.model_validate({}).text is None


class TestNotionRichText:
    def test_extracts_plain_text(self):
        prop = {"rich_text": [{"plain_text": "Test summary"}]}
        assert NotionRichText.model_validate(prop).text == "Test summary"

    def test_returns_none_for_empty(self):
        assert NotionRichText.model_validate({"rich_text": []}).text is None


class TestNotionSelect:
    def test_extracts_name(self):
        prop = {"select": {"name": "In Progress"}}
        assert NotionSelect.model_validate(prop).name == "In Progress"

    def test_returns_none_for_null(self):
        assert NotionSelect.model_validate({"select": None}).name is None


class TestNotionMultiSelect:
    def test_extracts_names(self):
        prop = {"multi_select": [{"name": "Tag1"}, {"name": "Tag2"}]}
        assert NotionMultiSelect.model_validate(prop).names == ["Tag1", "Tag2"]

    def test_returns_empty_for_empty(self):
        assert NotionMultiSelect.model_validate({"multi_select": []}).names == []


class TestNotionUrl:
    def test_extracts_url(self):
        prop = {"url": "https://example.com"}
        assert NotionUrl.model_validate(prop).url == "https://example.com"

    def test_returns_none_for_null(self):
        assert NotionUrl.model_validate({"url": None}).url is None


class TestNotionDate:
    def test_extracts_start(self):
        prop = {"date": {"start": "2026-04-15"}}
        assert NotionDate.model_validate(prop).start == "2026-04-15"

    def test_returns_none_for_null(self):
        assert NotionDate.model_validate({"date": None}).start is None


class TestNotionStatus:
    def test_extracts_name(self):
        prop = {"status": {"name": "Active"}}
        assert NotionStatus.model_validate(prop).name == "Active"

    def test_returns_none_for_null(self):
        assert NotionStatus.model_validate({"status": None}).name is None
```

- [ ] **Step 2: Run to verify tests fail**

Run: `pytest tests/test_integrations.py::TestNotionTitle::test_extracts_plain_text -v`
Expected: FAIL — `NotionTitle` doesn't exist yet.

- [ ] **Step 3: Add Notion property models to schemas.py**

Add before the `# --- Resource response models` section in `src/schemas.py`:

```python
from pydantic import ConfigDict

# --- Notion API property models (parse raw Notion property dicts) ---


class NotionPropertyValue(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NotionTitle(NotionPropertyValue):
    title: list[dict] = []

    @property
    def text(self) -> str | None:
        return self.title[0].get("plain_text") if self.title else None


class NotionRichText(NotionPropertyValue):
    rich_text: list[dict] = []

    @property
    def text(self) -> str | None:
        return self.rich_text[0].get("plain_text") if self.rich_text else None


class NotionSelect(NotionPropertyValue):
    select: dict | None = None

    @property
    def name(self) -> str | None:
        return self.select.get("name") if self.select else None


class NotionMultiSelect(NotionPropertyValue):
    multi_select: list[dict] = []

    @property
    def names(self) -> list[str]:
        return [item["name"] for item in self.multi_select if "name" in item]


class NotionUrl(NotionPropertyValue):
    url: str | None = None


class NotionDate(NotionPropertyValue):
    date: dict | None = None

    @property
    def start(self) -> str | None:
        return self.date.get("start") if self.date else None


class NotionStatus(NotionPropertyValue):
    status: dict | None = None

    @property
    def name(self) -> str | None:
        return self.status.get("name") if self.status else None
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `pytest tests/test_integrations.py -k "TestNotion" -v`
Expected: All 14 new tests pass.

- [ ] **Step 5: Replace _get_* helpers in integrations.py with model usage**

Remove these functions from `src/integrations.py`:
- `_get_title`
- `_get_rich_text`
- `_get_select`
- `_get_multi_select`
- `_get_url`
- `_get_date_start`
- `_get_status`

Update the import at top of `src/integrations.py` to include Notion property models:
```python
from .schemas import (
    JiraTaskData, NotionMeetingData, NotionTaskData,
    NotionTitle, NotionRichText, NotionSelect, NotionMultiSelect,
    NotionUrl, NotionDate, NotionStatus,
)
```

Update `fetch_tasks` method in `NotionClient`:
```python
def fetch_tasks(self) -> list[NotionTaskData]:
    """Query Tasks DB, return normalised NotionTaskData models."""
    if not self._token:
        raise ConfigurationError("Notion token not configured")

    try:
        pages = collect_paginated_api(
            self._query_database, database_id=self._tasks_db_id
        )
        tasks = []
        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})

            jira_url = NotionUrl.model_validate(props.get("Jira", {})).url
            task = NotionTaskData(
                notion_id=page_id,
                name=NotionTitle.model_validate(props.get("Task", {})).text,
                status=NotionStatus.model_validate(props.get("Status", {})).name,
                priority=NotionSelect.model_validate(props.get("Priority", {})).name,
                due_date=NotionDate.model_validate(props.get("Due date", {})).start,
                jira_url=jira_url,
                jira_key=_extract_jira_key(jira_url),
            )
            tasks.append(task)
        return tasks
    except APIResponseError as e:
        logger.warning("Notion fetch_tasks failed: %s", e)
        return []
```

Update `fetch_meetings` method:
```python
def fetch_meetings(self) -> list[NotionMeetingData]:
    """Query Meeting Notes DB, return normalised NotionMeetingData models."""
    if not self._token:
        raise ConfigurationError("Notion token not configured")

    try:
        pages = collect_paginated_api(
            self._query_database, database_id=self._meetings_db_id
        )
        meetings = []
        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})

            meeting = NotionMeetingData(
                notion_id=page_id,
                title=NotionTitle.model_validate(props.get("Meeting name", {})).text,
                categories=NotionMultiSelect.model_validate(props.get("Category", {})).names,
                summary=NotionRichText.model_validate(props.get("Summary", {})).text,
                krisp_url=NotionUrl.model_validate(props.get("Krisp URL", {})).url,
                date=NotionDate.model_validate(props.get("Date", {})).start,
            )
            meetings.append(meeting)
        return meetings
    except APIResponseError as e:
        logger.warning("Notion fetch_meetings failed: %s", e)
        return []
```

- [ ] **Step 6: Update test_integrations.py — remove old helper tests**

Remove these test functions from `tests/test_integrations.py`:
- `test_get_title`
- `test_get_rich_text`
- `test_get_select`
- `test_get_multi_select`
- `test_get_url`
- `test_get_date_start`
- `test_get_status`

Keep `test_extract_jira_key_from_url` — it still tests the `_extract_jira_key` function which remains.

- [ ] **Step 7: Run full integration test suite**

Run: `pytest tests/test_integrations.py tests/test_services.py -v`
Expected: All tests pass. The `fetch_tasks` and `fetch_meetings` tests use mock page data and assert on the returned `NotionTaskData`/`NotionMeetingData` fields — the models are identical, only the internal parsing changed.

- [ ] **Step 8: Commit**

```
git add src/schemas.py src/integrations.py tests/test_integrations.py
git commit -m "refactor: Notion property Pydantic models replace _get_* helpers

Add NotionTitle, NotionRichText, NotionSelect, NotionMultiSelect,
NotionUrl, NotionDate, NotionStatus models to schemas.py. Replace
8 manual dict-traversal helpers in integrations.py."
```

---

### Task 7: resources.py cleanup

**Files:**
- Modify: `src/resources.py`
- Test: `tests/test_resources.py` (no changes needed)

- [ ] **Step 1: Update resources.py**

Replace the full file:

```python
from sqlmodel import col, select

from .config import settings
from .database import get_session
from .mcp_instance import mcp
from .models import WizardSession
from .repositories import NoteRepository, TaskRepository
from .schemas import (
    BlockedTasksResource,
    ConfigResource,
    NoteDetail,
    OpenTasksResource,
    SessionResource,
    TaskContextResource,
)

task_repo = TaskRepository()
note_repo = NoteRepository()


def current_session() -> SessionResource:
    """Active session with open/blocked task counts."""
    with get_session() as db:
        stmt = (
            select(WizardSession)
            .where(WizardSession.summary == None)  # noqa: E711
            .order_by(col(WizardSession.created_at).desc())
            .limit(1)
        )
        session = db.exec(stmt).first()
        if session is None:
            return SessionResource(
                session_id=None, open_task_count=0, blocked_task_count=0
            )
        return SessionResource(
            session_id=session.id,
            open_task_count=len(task_repo.get_open_task_contexts(db)),
            blocked_task_count=len(task_repo.get_blocked_task_contexts(db)),
        )


def open_tasks() -> OpenTasksResource:
    """All open tasks with status and priority."""
    with get_session() as db:
        return OpenTasksResource(tasks=task_repo.get_open_task_contexts(db))


def blocked_tasks() -> BlockedTasksResource:
    """All blocked tasks."""
    with get_session() as db:
        return BlockedTasksResource(tasks=task_repo.get_blocked_task_contexts(db))


def task_context(task_id: int) -> TaskContextResource:
    """Full task detail — metadata, notes, history."""
    with get_session() as db:
        task = task_repo.get_by_id(db, task_id)
        task_ctx = task_repo.build_task_context(db, task)
        notes = note_repo.get_for_task(db, task_id=task.id, source_id=task.source_id)
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


def wizard_config() -> ConfigResource:
    """Current config — enabled integrations, active sources, database path."""
    return ConfigResource(
        jira_enabled=bool(settings.jira.token),
        notion_enabled=bool(settings.notion.token),
        scrubbing_enabled=settings.scrubbing.enabled,
        database_path=settings.db,
    )


mcp.resource("wizard://session/current")(current_session)
mcp.resource("wizard://tasks/open")(open_tasks)
mcp.resource("wizard://tasks/blocked")(blocked_tasks)
mcp.resource("wizard://tasks/{task_id}/context")(task_context)
mcp.resource("wizard://config")(wizard_config)
```

Changes from original:
- `_get_mcp()` wrapper replaced with direct `from .mcp_instance import mcp`
- `_task_repo` renamed to `task_repo`, `_note_repo` renamed to `note_repo`
- `_mcp` variable replaced with direct `mcp` usage
- `from .config import settings` moved to top-level (was inside `wizard_config`)

- [ ] **Step 2: Run resource tests**

Run: `pytest tests/test_resources.py -v`
Expected: All 5 tests pass. Tests patch `src.resources.get_session` — the repo instances are module-level so no patch change needed.

- [ ] **Step 3: Commit**

```
git add src/resources.py
git commit -m "refactor: resources.py drop _ prefixes, direct mcp import

Replace _get_mcp() with direct import, rename _task_repo/_note_repo,
move config import to top-level."
```

---

### Task 8: tools.py — @lru_cache singletons + top-level imports + enum params

**Files:**
- Modify: `src/tools.py`
- Modify: `tests/test_tools.py`

This is the largest task. Three changes at once because they all touch the same file and the test patches need a single coherent update.

- [ ] **Step 1: Verify FastMCP enum handling**

Before changing tool signatures, confirm FastMCP coerces string values to enum params:

Run: `python3 -c "from fastmcp import FastMCP; from enum import Enum; exec(\"class P(str,Enum):\\n HIGH='high'\\n LOW='low'\"); app=FastMCP('t'); app.tool()(lambda p=P.HIGH: p.value); import json; print(json.dumps(app._tool_manager._tools, default=str, indent=2))"`

If FastMCP exposes enum params as string values in the MCP tool schema, proceed with enum params. If not, keep string params with direct `Enum(value)` calls (no manual list-building).

- [ ] **Step 2: Rewrite tools.py**

Replace the full file content of `src/tools.py`:

```python
import logging
from functools import lru_cache

from fastmcp import Context
from fastmcp.server.dependencies import CurrentContext
from sqlmodel import select

from .config import settings
from .database import get_session
from .integrations import JiraClient, NotionClient
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
from .repositories import MeetingRepository, NoteRepository, TaskRepository
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
from .security import SecurityService
from .services import SyncService, WriteBackService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached dependency singletons — one instance per process.
# Tests call <func>.cache_clear() to reset.
# Config changes require restart.
# ---------------------------------------------------------------------------


@lru_cache
def jira_client() -> JiraClient:
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
    )


@lru_cache
def notion_client() -> NotionClient:
    return NotionClient(
        token=settings.notion.token,
        daily_page_id=settings.notion.daily_page_id,
        tasks_db_id=settings.notion.tasks_db_id,
        meetings_db_id=settings.notion.meetings_db_id,
    )


@lru_cache
def security() -> SecurityService:
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
    )


@lru_cache
def sync_service() -> SyncService:
    return SyncService(
        jira=jira_client(), notion=notion_client(), security=security()
    )


@lru_cache
def writeback() -> WriteBackService:
    return WriteBackService(jira=jira_client(), notion=notion_client())


@lru_cache
def task_repo() -> TaskRepository:
    return TaskRepository()


@lru_cache
def meeting_repo() -> MeetingRepository:
    return MeetingRepository()


@lru_cache
def note_repo() -> NoteRepository:
    return NoteRepository()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def session_start(ctx: Context = CurrentContext()) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    with get_session() as db:
        ctx.info("Creating new session")
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        ctx.report_progress(1, 3)
        ctx.info("Syncing integrations")
        sync_results = sync_service().sync_all(db)
        ctx.report_progress(2, 3)

        ctx.report_progress(3, 3)
        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
        )


def task_start(task_id: int) -> TaskStartResponse:
    """Returns full task context + all prior notes for compounding context."""
    with get_session() as db:
        task = task_repo().get_by_id(db, task_id)
        task_ctx = task_repo().build_task_context(db, task)

        notes = note_repo().get_for_task(db, task_id=task.id, source_id=task.source_id)
        notes_by_type: dict[str, int] = {}
        for note in notes:
            key = note.note_type.value
            notes_by_type[key] = notes_by_type.get(key, 0) + 1

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

        return TaskStartResponse(
            task=task_ctx,
            compounding=len(notes) > 0,
            notes_by_type=notes_by_type,
            prior_notes=prior_notes,
        )


def save_note(task_id: int, note_type: NoteType, content: str) -> SaveNoteResponse:
    """Scrubs and persists a note. note_type: investigation|decision|docs|learnings|session_summary."""
    with get_session() as db:
        task = task_repo().get_by_id(db, task_id)
        clean = security().scrub(content).clean
        note = Note(
            note_type=note_type,
            content=clean,
            task_id=task.id,
            source_id=task.source_id,
        )
        saved = note_repo().save(db, note)
        assert saved.id is not None
        return SaveNoteResponse(note_id=saved.id)


def update_task_status(task_id: int, new_status: TaskStatus) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back."""
    with get_session() as db:
        task = task_repo().get_by_id(db, task_id)
        task.status = new_status
        db.add(task)
        db.flush()
        db.refresh(task)
        assert task.id is not None

        jira_wb = writeback().push_task_status(task)
        notion_wb = writeback().push_task_status_to_notion(task)

        return UpdateTaskStatusResponse(
            task_id=task.id,
            new_status=task.status,
            jira_write_back=jira_wb,
            notion_write_back=notion_wb,
        )


def get_meeting(meeting_id: int) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks."""
    with get_session() as db:
        meeting = meeting_repo().get_by_id(db, meeting_id)
        assert meeting.id is not None

        linked_tasks = [
            task_repo().build_task_context(db, t)
            for t in meeting.tasks
            if t.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
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


def save_meeting_summary(
    meeting_id: int, session_id: int, summary: str, task_ids: list[int] | None = None
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
    with get_session() as db:
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


def session_end(
    session_id: int, summary: str, ctx: Context = CurrentContext()
) -> SessionEndResponse:
    """Persists session summary note and attempts Notion daily page write-back."""
    with get_session() as db:
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        ctx.info("Saving session summary")
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

        ctx.info("Writing back to Notion")
        wb_result = writeback().push_session_summary(session)

        return SessionEndResponse(
            note_id=saved.id,
            notion_write_back=wb_result,
        )


def ingest_meeting(
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
    ctx: Context = CurrentContext(),
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    with get_session() as db:
        ctx.info("Scrubbing and storing meeting")
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

        ctx.info("Writing back to Notion")
        wb_result = writeback().push_meeting_to_notion(meeting)
        if wb_result.page_id:
            meeting.notion_id = wb_result.page_id
            db.flush()

        return IngestMeetingResponse(
            meeting_id=meeting.id,
            already_existed=already_existed,
            notion_write_back=wb_result,
        )


def create_task(
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
    ctx: Context = CurrentContext(),
) -> CreateTaskResponse:
    """Creates a task, optionally links to a meeting, writes to Notion."""
    with get_session() as db:
        ctx.info("Creating task")
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

        ctx.info("Writing back to Notion")
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

- [ ] **Step 3: Update test_tools.py**

Update the `_patch_tools` helper — rename patched names from `_sync_service`/`_writeback` to `sync_service`/`writeback`:

```python
def _patch_tools(db_session, sync=None, wb=None):
    """Patch tools module dependencies with test doubles."""
    sync_mock = sync or MagicMock()
    wb_mock = wb or MagicMock()

    patches = {
        "get_session": _mock_session(db_session),
        "sync_service": lambda: sync_mock,
        "writeback": lambda: wb_mock,
    }
    return patches, sync_mock, wb_mock
```

Update `test_save_note_scrubs_and_persists` — `note_type` is now `NoteType` enum:

```python
def test_save_note_scrubs_and_persists(db_session):
    from src.tools import save_note
    from src.models import Task, Note, NoteType

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("src.tools", **patches):
        result = save_note(
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="john@example.com found a bug",
        )

    assert result.note_id is not None

    saved_note = db_session.get(Note, result.note_id)
    assert "john@example.com" not in saved_note.content
    assert "[EMAIL_1]" in saved_note.content
```

Update `test_update_task_status_persists_and_writebacks` — `new_status` is now `TaskStatus`:

```python
    # Change this line:
    result = update_task_status(task_id=task_id, new_status="done")
    # To:
    result = update_task_status(task_id=task_id, new_status=TaskStatus.DONE)
```

Update `test_update_task_status_dual_writeback` similarly:

```python
    # Change:
    result = update_task_status(task_id=task.id, new_status="done")
    # To:
    result = update_task_status(task_id=task.id, new_status=TaskStatus.DONE)
```

Update `test_ingest_meeting_creates_meeting` — `category` is now `MeetingCategory`:

```python
    from src.models import MeetingCategory
    # ...
    result = ingest_meeting(
        title="Sprint Planning",
        content="john@example.com reported a bug",
        source_id="krisp-abc",
        source_url="https://krisp.ai/m/abc",
        category=MeetingCategory.PLANNING,
        ctx=_mock_context(),
    )
```

Update `test_create_task_creates_and_links` — `priority` is now `TaskPriority`:

```python
    from src.models import TaskPriority
    # ...
    result = create_task(
        name="Fix john@example.com auth bug",
        priority=TaskPriority.HIGH,
        meeting_id=meeting_id,
        ctx=_mock_context(),
    )
```

Update `test_compounding_loop_across_two_sessions` — `save_note` and `update_task_status`:

```python
    from src.models import NoteType
    # ... inside the patch block:
    save_note(task_id=task_id, note_type=NoteType.INVESTIGATION, content="Found the root cause")
    update_task_status(task_id=task_id, new_status=TaskStatus.IN_PROGRESS)
```

- [ ] **Step 4: Run all tools tests**

Run: `pytest tests/test_tools.py -v`
Expected: All 14 tests pass.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass across all test files.

- [ ] **Step 6: Commit**

```
git add src/tools.py tests/test_tools.py
git commit -m "refactor: @lru_cache singletons, top-level imports, enum tool params

Replace 8 global+guard singletons with @lru_cache. Move all in-function
imports to top-level. Tool params now use enum types directly (NoteType,
TaskStatus, MeetingCategory, TaskPriority, TaskCategory) eliminating
manual validation boilerplate."
```

---

### Task 9: Final verification

**Files:** None — verification only.

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Verify no remaining dataclass usage**

Run: `grep -r "from dataclasses import" src/`
Expected: No output.

- [ ] **Step 3: Verify no remaining typing.Optional/Dict/List/Tuple**

Run: `grep -rn "from typing import.*Optional\|from typing import.*Dict\|from typing import.*List\|from typing import.*Tuple" src/`
Expected: No output (config.py still imports `Any`, which is correct).

- [ ] **Step 4: Verify no remaining __future__ imports**

Run: `grep -rn "from __future__" src/`
Expected: No output.

- [ ] **Step 5: Verify no remaining _get_mcp pattern**

Run: `grep -rn "_get_mcp" src/`
Expected: No output.

- [ ] **Step 6: Verify no remaining global singleton pattern**

Run: `grep -rn "global _" src/`
Expected: No output.

- [ ] **Step 7: Commit (if any stragglers fixed)**

Only if verification steps found issues that required fixes.
