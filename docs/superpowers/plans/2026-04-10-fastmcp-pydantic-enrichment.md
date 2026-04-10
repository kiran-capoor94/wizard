# FastMCP & Pydantic Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich Wizard v1.1.0 with Pydantic integration models, a mapper module, FastMCP Resources, Prompts, and Context — replacing raw dicts and unlocking the full FastMCP feature surface.

**Architecture:** Bottom-up type safety first (integration models, mappers), then FastMCP features built on typed data (resources, tool return types, prompts, context). Each layer composes cleanly — no rework.

**Tech Stack:** FastMCP 3.2.0+, Pydantic v2 (via pydantic-settings + sqlmodel), SQLModel, pytest, respx

**Spec:** `docs/superpowers/specs/2026-04-10-fastmcp-pydantic-enrichment-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/mappers.py` | Bidirectional status/priority/category mappers between Jira/Notion and internal enums |
| `src/resources.py` | FastMCP resource handlers — read-only data exposed via URIs |
| `src/prompts.py` | FastMCP prompt definitions — reasoning scaffolding for Claude Code |
| `tests/test_mappers.py` | Mapper bidirectional correctness tests |
| `tests/test_resources.py` | Resource handler tests |
| `tests/test_prompts.py` | Prompt registration and return type tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/schemas.py` | Add `JiraTaskData`, `NotionTaskData`, `NotionMeetingData` (integration models) + `SessionResource`, `TaskContextResource`, `OpenTasksResource`, `BlockedTasksResource`, `ConfigResource` (resource models) |
| `src/integrations.py:35-56,173-200,202-228` | Return Pydantic models from `fetch_*()` methods |
| `src/services.py:17-80,104-261,264-391` | Remove mapping dicts, use mappers, use typed attribute access |
| `src/tools.py:132-457` | Return Pydantic models directly, inject Context into 4 tools |
| `server.py:1-5` | Import `src.resources` and `src.prompts` to register handlers |
| `tests/test_integrations.py:39-68,124-260` | Assert on Pydantic model attributes instead of dict keys |
| `tests/test_services.py:14-89,167-270` | Use Pydantic models as mock return values |
| `tests/test_tools.py:34-496` | Assert on Pydantic model fields instead of dict keys |

---

### Task 1: Integration Response Models

**Files:**
- Modify: `src/schemas.py:1-5` (add imports and models after existing imports)
- Test: `tests/test_integrations.py` (update assertions)
- Modify: `src/integrations.py:35,173,202` (update return types)

- [ ] **Step 1: Add integration response models to schemas.py**

Add after line 5 (`from .models import ...`) and before the `SourceSyncStatus` class in `src/schemas.py`:

```python
# --- Integration response models (typed outputs from Jira/Notion clients) ---


class JiraTaskData(BaseModel):
    key: str
    summary: str
    status: str
    priority: str
    issue_type: str
    url: str = ""


class NotionTaskData(BaseModel):
    notion_id: str
    name: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: str | None = None
    jira_url: str | None = None
    jira_key: str | None = None


class NotionMeetingData(BaseModel):
    notion_id: str
    title: str | None = None
    categories: list[str] = []
    summary: str | None = None
    krisp_url: str | None = None
    date: str | None = None
```

- [ ] **Step 2: Run tests to confirm nothing broke**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All existing tests pass (models are added but not yet used)

- [ ] **Step 3: Update JiraClient.fetch_open_tasks() to return list[JiraTaskData]**

In `src/integrations.py`, change `fetch_open_tasks` (line 35):

```python
    def fetch_open_tasks(self) -> list["JiraTaskData"]:
        from .schemas import JiraTaskData

        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        try:
            jql = f"project={self._project_key} AND statusCategory != Done ORDER BY priority DESC"
            response = self._client.get("/search", params={"jql": jql, "maxResults": 50})
            response.raise_for_status()
            issues = response.json().get("issues", [])
            return [
                JiraTaskData(
                    key=issue["key"],
                    summary=issue["fields"]["summary"],
                    status=issue["fields"]["status"]["name"],
                    priority=issue["fields"]["priority"]["name"],
                    issue_type=issue["fields"]["issuetype"]["name"],
                    url=issue["fields"].get("self", ""),
                )
                for issue in issues
            ]
        except httpx.HTTPError as e:
            logger.warning("Jira fetch_open_tasks failed: %s", e)
            return []
```

- [ ] **Step 4: Update test_integrations.py Jira assertions to use attribute access**

In `tests/test_integrations.py`, update `test_jira_fetch_open_tasks_returns_list` (lines 60-66):

```python
    assert len(tasks) == 1
    assert tasks[0].key == "ENG-1"
    assert tasks[0].summary == "Fix login"
    assert tasks[0].status == "In Progress"
    assert tasks[0].priority == "High"
    assert tasks[0].issue_type == "Bug"
```

- [ ] **Step 5: Run Jira integration tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py -x -q -k jira`
Expected: All Jira tests pass

- [ ] **Step 6: Update NotionClient.fetch_tasks() to return list[NotionTaskData]**

In `src/integrations.py`, change `fetch_tasks` (line 173):

```python
    def fetch_tasks(self) -> list["NotionTaskData"]:
        """Query Tasks DB, return normalised NotionTaskData models."""
        from .schemas import NotionTaskData

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

                task = NotionTaskData(
                    notion_id=page_id,
                    name=_get_title(props, "Task"),
                    status=_get_status(props, "Status"),
                    priority=_get_select(props, "Priority"),
                    due_date=_get_date_start(props, "Due date"),
                    jira_url=_get_url(props, "Jira"),
                    jira_key=_extract_jira_key(_get_url(props, "Jira")),
                )
                tasks.append(task)
            return tasks
        except APIResponseError as e:
            logger.warning("Notion fetch_tasks failed: %s", e)
            return []
```

- [ ] **Step 7: Update NotionClient.fetch_meetings() to return list[NotionMeetingData]**

In `src/integrations.py`, change `fetch_meetings` (line 202):

```python
    def fetch_meetings(self) -> list["NotionMeetingData"]:
        """Query Meeting Notes DB, return normalised NotionMeetingData models."""
        from .schemas import NotionMeetingData

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
                    title=_get_title(props, "Meeting name"),
                    categories=_get_multi_select(props, "Category") or [],
                    summary=_get_rich_text(props, "Summary"),
                    krisp_url=_get_url(props, "Krisp URL"),
                    date=_get_date_start(props, "Date"),
                )
                meetings.append(meeting)
            return meetings
        except APIResponseError as e:
            logger.warning("Notion fetch_meetings failed: %s", e)
            return []
```

- [ ] **Step 8: Update test_integrations.py Notion assertions to use attribute access**

In `tests/test_integrations.py`, update `test_notion_fetch_tasks_returns_list_of_dicts` (lines 145-152) to:

```python
    assert len(tasks) == 1
    assert tasks[0].notion_id == "task-uuid-1"
    assert tasks[0].name == "Implement auth"
    assert tasks[0].status == "In Progress"
    assert tasks[0].priority == "High"
    assert tasks[0].due_date == "2026-04-15"
    assert tasks[0].jira_url == "https://org.atlassian.net/browse/ENG-123"
    assert tasks[0].jira_key == "ENG-123"
```

Update `test_notion_fetch_tasks_handles_missing_properties` (lines 174-181) to:

```python
    assert len(tasks) == 1
    assert tasks[0].notion_id == "task-uuid-2"
    assert tasks[0].name == "Task with minimal props"
    assert tasks[0].status is None
    assert tasks[0].priority is None
    assert tasks[0].due_date is None
    assert tasks[0].jira_url is None
    assert tasks[0].jira_key is None
```

Update `test_notion_fetch_meetings_returns_list_of_dicts` (lines 228-234) to:

```python
    assert len(meetings) == 1
    assert meetings[0].notion_id == "meeting-uuid-1"
    assert meetings[0].title == "Sprint Planning"
    assert meetings[0].categories == ["Planning", "Standup"]
    assert meetings[0].summary == "Discussed Q2 roadmap"
    assert meetings[0].krisp_url == "https://krisp.ai/m/abc123"
    assert meetings[0].date == "2026-04-10"
```

Update `test_notion_fetch_meetings_handles_missing_properties` (lines 255-261) to:

```python
    assert len(meetings) == 1
    assert meetings[0].notion_id == "meeting-uuid-2"
    assert meetings[0].title == "Minimal meeting"
    assert meetings[0].categories == []
    assert meetings[0].summary is None
    assert meetings[0].krisp_url is None
    assert meetings[0].date is None
```

- [ ] **Step 9: Run all integration tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py -x -q`
Expected: All tests pass

- [ ] **Step 10: Update test_services.py mock return values to use Pydantic models**

Add import at the top of `tests/test_services.py`:

```python
from src.schemas import JiraTaskData, NotionTaskData, NotionMeetingData
```

Replace **every** Jira mock dict (pattern: `jira.fetch_open_tasks.return_value = [{...}]`) with `JiraTaskData(...)`. Replace **every** Notion task mock dict (pattern: `notion.fetch_tasks.return_value = [{...}]`) with `NotionTaskData(...)`. Replace **every** Notion meeting mock dict (pattern: `notion.fetch_meetings.return_value = [{...}]`) with `NotionMeetingData(...)`.

Example — in `test_sync_creates_new_task_from_jira`:

```python
    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-1", summary="Fix login", status="In Progress",
        priority="High", issue_type="Bug",
        url="https://jira.example.com/browse/ENG-1",
    )]
```

Apply this transformation to all ~15 occurrences in the file. Every `[{` that's a mock return value becomes `[JiraTaskData(`, `[NotionTaskData(`, or `[NotionMeetingData(`.

- [ ] **Step 11: Run service tests (expect failures — services still use dict access)**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_services.py -x -q`
Expected: FAIL — services try `raw["summary"]` on Pydantic model objects

- [ ] **Step 12: Update services.py to use typed attribute access**

In `src/services.py`, update `_sync_jira` (lines 107-132). Replace all dict access with attribute access:

- `raw["summary"]` → `raw.summary`
- `raw["key"]` → `raw.key`
- `raw["priority"]` → `raw.priority`
- `raw["status"]` → `raw.status`
- `raw.get("url")` → `raw.url`

Update `_sync_notion_tasks` (lines 138-196). Replace all dict access:

- `raw.get("name")` → `raw.name`
- `raw.get("jira_key")` → `raw.jira_key`
- `raw.get("jira_url")` → `raw.jira_url`
- `raw.get("notion_id")` → `raw.notion_id`
- `raw.get("priority")` → `raw.priority`
- `raw.get("due_date")` → `raw.due_date`
- `raw.get("status")` → `raw.status`

Update `_sync_notion_meetings` (lines 201-261). Replace all dict access:

- `raw.get("title")` → `raw.title`
- `raw.get("notion_id")` → `raw.notion_id`
- `raw.get("krisp_url")` → `raw.krisp_url`
- `raw.get("categories")` → `raw.categories`
- `raw.get("summary")` → `raw.summary`

- [ ] **Step 13: Run all tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 14: Commit**

```bash
git add src/schemas.py src/integrations.py src/services.py tests/test_integrations.py tests/test_services.py
git commit -m "feat: replace raw dicts with Pydantic integration response models

JiraClient, NotionClient now return typed JiraTaskData, NotionTaskData,
NotionMeetingData. Services use attribute access instead of dict keys."
```

---

### Task 2: Mapper Module

**Files:**
- Create: `src/mappers.py`
- Create: `tests/test_mappers.py`
- Modify: `src/services.py:17-80,104-132,134-196,264-391`

- [ ] **Step 1: Write failing tests for mappers**

Create `tests/test_mappers.py`:

```python
import logging

from src.mappers import StatusMapper, PriorityMapper, MeetingCategoryMapper
from src.models import TaskStatus, TaskPriority, MeetingCategory


# ============================================================================
# StatusMapper
# ============================================================================


class TestStatusMapperJiraToLocal:
    def test_known_statuses(self):
        assert StatusMapper.jira_to_local("to do") == TaskStatus.TODO
        assert StatusMapper.jira_to_local("in progress") == TaskStatus.IN_PROGRESS
        assert StatusMapper.jira_to_local("blocked") == TaskStatus.BLOCKED
        assert StatusMapper.jira_to_local("done") == TaskStatus.DONE

    def test_case_insensitive(self):
        assert StatusMapper.jira_to_local("To Do") == TaskStatus.TODO
        assert StatusMapper.jira_to_local("IN PROGRESS") == TaskStatus.IN_PROGRESS

    def test_unknown_falls_back_to_todo(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = StatusMapper.jira_to_local("unknown-status")
        assert result == TaskStatus.TODO
        assert "unknown-status" in caplog.text


class TestStatusMapperNotionToLocal:
    def test_known_statuses(self):
        assert StatusMapper.notion_to_local("not started") == TaskStatus.TODO
        assert StatusMapper.notion_to_local("in progress") == TaskStatus.IN_PROGRESS
        assert StatusMapper.notion_to_local("blocked") == TaskStatus.BLOCKED
        assert StatusMapper.notion_to_local("done") == TaskStatus.DONE
        assert StatusMapper.notion_to_local("archive") == TaskStatus.ARCHIVED

    def test_case_insensitive(self):
        assert StatusMapper.notion_to_local("Not Started") == TaskStatus.TODO

    def test_unknown_falls_back_to_todo(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = StatusMapper.notion_to_local("unknown")
        assert result == TaskStatus.TODO
        assert "unknown" in caplog.text


class TestStatusMapperLocalToExternal:
    def test_local_to_jira(self):
        assert StatusMapper.local_to_jira(TaskStatus.TODO) == "To Do"
        assert StatusMapper.local_to_jira(TaskStatus.IN_PROGRESS) == "In Progress"
        assert StatusMapper.local_to_jira(TaskStatus.BLOCKED) == "Blocked"
        assert StatusMapper.local_to_jira(TaskStatus.DONE) == "Done"
        assert StatusMapper.local_to_jira(TaskStatus.ARCHIVED) == "Done"

    def test_local_to_notion(self):
        assert StatusMapper.local_to_notion(TaskStatus.TODO) == "Not started"
        assert StatusMapper.local_to_notion(TaskStatus.IN_PROGRESS) == "In progress"
        assert StatusMapper.local_to_notion(TaskStatus.BLOCKED) == "Blocked"
        assert StatusMapper.local_to_notion(TaskStatus.DONE) == "Done"
        assert StatusMapper.local_to_notion(TaskStatus.ARCHIVED) == "Archive"


# ============================================================================
# PriorityMapper
# ============================================================================


class TestPriorityMapperJiraToLocal:
    def test_known_priorities(self):
        assert PriorityMapper.jira_to_local("highest") == TaskPriority.HIGH
        assert PriorityMapper.jira_to_local("high") == TaskPriority.HIGH
        assert PriorityMapper.jira_to_local("medium") == TaskPriority.MEDIUM
        assert PriorityMapper.jira_to_local("low") == TaskPriority.LOW
        assert PriorityMapper.jira_to_local("lowest") == TaskPriority.LOW

    def test_case_insensitive(self):
        assert PriorityMapper.jira_to_local("HIGH") == TaskPriority.HIGH

    def test_unknown_falls_back_to_medium(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = PriorityMapper.jira_to_local("critical")
        assert result == TaskPriority.MEDIUM
        assert "critical" in caplog.text


class TestPriorityMapperNotionToLocal:
    def test_known_priorities(self):
        assert PriorityMapper.notion_to_local("high") == TaskPriority.HIGH
        assert PriorityMapper.notion_to_local("medium") == TaskPriority.MEDIUM
        assert PriorityMapper.notion_to_local("low") == TaskPriority.LOW

    def test_case_insensitive(self):
        assert PriorityMapper.notion_to_local("High") == TaskPriority.HIGH

    def test_unknown_falls_back_to_medium(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = PriorityMapper.notion_to_local("urgent")
        assert result == TaskPriority.MEDIUM
        assert "urgent" in caplog.text


class TestPriorityMapperLocalToNotion:
    def test_all_priorities(self):
        assert PriorityMapper.local_to_notion(TaskPriority.HIGH) == "High"
        assert PriorityMapper.local_to_notion(TaskPriority.MEDIUM) == "Medium"
        assert PriorityMapper.local_to_notion(TaskPriority.LOW) == "Low"


# ============================================================================
# MeetingCategoryMapper
# ============================================================================


class TestMeetingCategoryMapperNotionToLocal:
    def test_known_categories(self):
        assert MeetingCategoryMapper.notion_to_local("standup") == MeetingCategory.STANDUP
        assert MeetingCategoryMapper.notion_to_local("planning") == MeetingCategory.PLANNING
        assert MeetingCategoryMapper.notion_to_local("retro") == MeetingCategory.RETRO

    def test_known_general_mappings(self):
        assert MeetingCategoryMapper.notion_to_local("presentation") == MeetingCategory.GENERAL
        assert MeetingCategoryMapper.notion_to_local("customer call") == MeetingCategory.GENERAL

    def test_case_insensitive(self):
        assert MeetingCategoryMapper.notion_to_local("Standup") == MeetingCategory.STANDUP

    def test_unknown_falls_back_to_general(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = MeetingCategoryMapper.notion_to_local("xyz-unknown")
        assert result == MeetingCategory.GENERAL


class TestMeetingCategoryMapperLocalToNotion:
    def test_mappable_categories(self):
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.STANDUP) == "Standup"
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.PLANNING) == "Planning"
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.RETRO) == "Retro"

    def test_unmappable_returns_none(self):
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.ONE_ON_ONE) is None
        assert MeetingCategoryMapper.local_to_notion(MeetingCategory.GENERAL) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_mappers.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.mappers'`

- [ ] **Step 3: Implement mapper module**

Create `src/mappers.py`:

```python
import logging

from .models import MeetingCategory, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

_JIRA_STATUS_MAP: dict[str, TaskStatus] = {
    "to do": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "blocked": TaskStatus.BLOCKED,
    "done": TaskStatus.DONE,
}

_JIRA_PRIORITY_MAP: dict[str, TaskPriority] = {
    "highest": TaskPriority.HIGH,
    "high": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
    "lowest": TaskPriority.LOW,
}

_NOTION_STATUS_MAP: dict[str, TaskStatus] = {
    "not started": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "blocked": TaskStatus.BLOCKED,
    "done": TaskStatus.DONE,
    "archive": TaskStatus.ARCHIVED,
}

_NOTION_PRIORITY_MAP: dict[str, TaskPriority] = {
    "high": TaskPriority.HIGH,
    "medium": TaskPriority.MEDIUM,
    "low": TaskPriority.LOW,
}

_LOCAL_TO_JIRA_STATUS: dict[str, str] = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "blocked": "Blocked",
    "done": "Done",
    "archived": "Done",
}

_LOCAL_TO_NOTION_STATUS: dict[str, str] = {
    "todo": "Not started",
    "in_progress": "In progress",
    "blocked": "Blocked",
    "done": "Done",
    "archived": "Archive",
}

_NOTION_MEETING_CATEGORY_MAP: dict[str, MeetingCategory] = {
    "standup": MeetingCategory.STANDUP,
    "planning": MeetingCategory.PLANNING,
    "retro": MeetingCategory.RETRO,
    "presentation": MeetingCategory.GENERAL,
    "customer call": MeetingCategory.GENERAL,
}

_LOCAL_TO_NOTION_MEETING_CATEGORY: dict[str, str | None] = {
    "standup": "Standup",
    "planning": "Planning",
    "retro": "Retro",
    "one_on_one": None,
    "general": None,
}


class StatusMapper:
    @staticmethod
    def jira_to_local(jira_status: str) -> TaskStatus:
        result = _JIRA_STATUS_MAP.get(jira_status.lower())
        if result is None:
            logger.warning("Unknown Jira status '%s', falling back to TODO", jira_status)
            return TaskStatus.TODO
        return result

    @staticmethod
    def notion_to_local(notion_status: str) -> TaskStatus:
        result = _NOTION_STATUS_MAP.get(notion_status.lower())
        if result is None:
            logger.warning("Unknown Notion status '%s', falling back to TODO", notion_status)
            return TaskStatus.TODO
        return result

    @staticmethod
    def local_to_jira(status: TaskStatus) -> str:
        return _LOCAL_TO_JIRA_STATUS[status.value]

    @staticmethod
    def local_to_notion(status: TaskStatus) -> str:
        return _LOCAL_TO_NOTION_STATUS[status.value]


class PriorityMapper:
    @staticmethod
    def jira_to_local(jira_priority: str) -> TaskPriority:
        result = _JIRA_PRIORITY_MAP.get(jira_priority.lower())
        if result is None:
            logger.warning("Unknown Jira priority '%s', falling back to MEDIUM", jira_priority)
            return TaskPriority.MEDIUM
        return result

    @staticmethod
    def notion_to_local(notion_priority: str) -> TaskPriority:
        result = _NOTION_PRIORITY_MAP.get(notion_priority.lower())
        if result is None:
            logger.warning("Unknown Notion priority '%s', falling back to MEDIUM", notion_priority)
            return TaskPriority.MEDIUM
        return result

    @staticmethod
    def local_to_notion(priority: TaskPriority) -> str:
        return priority.value.capitalize()


class MeetingCategoryMapper:
    @staticmethod
    def notion_to_local(notion_category: str) -> MeetingCategory:
        result = _NOTION_MEETING_CATEGORY_MAP.get(notion_category.lower())
        if result is None:
            logger.warning("Unknown Notion meeting category '%s', falling back to GENERAL", notion_category)
            return MeetingCategory.GENERAL
        return result

    @staticmethod
    def local_to_notion(category: MeetingCategory) -> str | None:
        return _LOCAL_TO_NOTION_MEETING_CATEGORY.get(category.value)
```

- [ ] **Step 4: Run mapper tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_mappers.py -x -v`
Expected: All mapper tests pass

- [ ] **Step 5: Update services.py to use mappers**

In `src/services.py`:

1. **Remove** all mapping dict definitions (lines 17-80 — everything from `_JIRA_STATUS_MAP` through `_LOCAL_TO_NOTION_MEETING_CATEGORY`).

2. **Add** import:

```python
from .mappers import StatusMapper, PriorityMapper, MeetingCategoryMapper
```

3. In `_sync_jira`, replace inline dict lookups with mapper calls:

```python
existing.priority = PriorityMapper.jira_to_local(raw.priority)
```
instead of `TaskPriority(_JIRA_PRIORITY_MAP.get(raw.priority.lower(), "medium"))`.

```python
priority=PriorityMapper.jira_to_local(raw.priority),
status=StatusMapper.jira_to_local(raw.status),
```
instead of `TaskPriority(_JIRA_PRIORITY_MAP.get(...))` and `TaskStatus(_JIRA_STATUS_MAP.get(...))`.

4. In `_sync_notion_tasks`, replace:

```python
priority = PriorityMapper.notion_to_local(raw_priority)
```
instead of `TaskPriority(_NOTION_PRIORITY_MAP.get(raw_priority.lower(), "medium"))`.

```python
status=StatusMapper.notion_to_local(raw_status),
```
instead of `TaskStatus(_NOTION_STATUS_MAP.get(raw_status.lower(), "todo"))`.

5. In `_sync_notion_meetings`, replace the category mapping loop:

```python
            raw_categories = raw.categories or []
            category = MeetingCategory.GENERAL
            for raw_cat in raw_categories:
                category = MeetingCategoryMapper.notion_to_local(raw_cat)
                if category != MeetingCategory.GENERAL:
                    break
```

6. In `WriteBackService.push_task_status`, replace:

```python
        jira_status = StatusMapper.local_to_jira(task.status)
```
Remove the `status_key` variable and the `if not jira_status` guard (mapper always returns a value).

7. In `WriteBackService.push_task_status_to_notion`, replace:

```python
        notion_status = StatusMapper.local_to_notion(task.status)
```
Remove the `status_key` variable and the `if not notion_status` guard.

8. In `WriteBackService.push_task_to_notion`, replace:

```python
        notion_status = StatusMapper.local_to_notion(task.status)
        priority_label = PriorityMapper.local_to_notion(task.priority)
```

9. In `WriteBackService.push_meeting_to_notion`, replace:

```python
        notion_category = MeetingCategoryMapper.local_to_notion(meeting.category)
        if not notion_category:
            return WriteBackStatus(
                ok=False,
                error=f"No Notion category mapping for '{meeting.category.value}'",
            )
```

- [ ] **Step 6: Run all tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/mappers.py tests/test_mappers.py src/services.py
git commit -m "refactor: extract mapping dicts into dedicated mapper module

StatusMapper, PriorityMapper, MeetingCategoryMapper replace inline dicts
in services.py. Unknown values fall back to sensible defaults with warnings."
```

---

### Task 3: Resource Response Models and Handlers

**Files:**
- Modify: `src/schemas.py` (add resource models)
- Create: `src/resources.py`
- Create: `tests/test_resources.py`
- Modify: `server.py`

- [ ] **Step 1: Add resource response models to schemas.py**

Add after the integration response models (before `SourceSyncStatus`) in `src/schemas.py`:

```python
# --- Resource response models (read-only data exposed via FastMCP URIs) ---


class SessionResource(BaseModel):
    session_id: Optional[int]
    open_task_count: int
    blocked_task_count: int


class TaskContextResource(BaseModel):
    task: "TaskContext"
    notes: list["NoteDetail"]


class OpenTasksResource(BaseModel):
    tasks: list["TaskContext"]


class BlockedTasksResource(BaseModel):
    tasks: list["TaskContext"]


class ConfigResource(BaseModel):
    jira_enabled: bool
    notion_enabled: bool
    scrubbing_enabled: bool
    database_path: str
```

- [ ] **Step 2: Write failing tests for resources**

Create `tests/test_resources.py`:

```python
from unittest.mock import patch
from contextlib import contextmanager


def _mock_session(db_session):
    @contextmanager
    def _inner():
        yield db_session
        db_session.flush()
    return _inner


def test_open_tasks_resource(db_session):
    from src.models import Task, TaskStatus
    from src.resources import open_tasks
    from src.schemas import OpenTasksResource

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()

    with patch("src.resources.get_session", _mock_session(db_session)):
        result = open_tasks()

    assert isinstance(result, OpenTasksResource)
    assert len(result.tasks) == 1
    assert result.tasks[0].name == "Fix auth"


def test_open_tasks_resource_empty(db_session):
    from src.resources import open_tasks
    from src.schemas import OpenTasksResource

    with patch("src.resources.get_session", _mock_session(db_session)):
        result = open_tasks()

    assert isinstance(result, OpenTasksResource)
    assert len(result.tasks) == 0


def test_blocked_tasks_resource(db_session):
    from src.models import Task, TaskStatus
    from src.resources import blocked_tasks
    from src.schemas import BlockedTasksResource

    task = Task(name="Blocked task", status=TaskStatus.BLOCKED)
    db_session.add(task)
    db_session.commit()

    with patch("src.resources.get_session", _mock_session(db_session)):
        result = blocked_tasks()

    assert isinstance(result, BlockedTasksResource)
    assert len(result.tasks) == 1
    assert result.tasks[0].name == "Blocked task"


def test_current_session_resource_active(db_session):
    from src.models import WizardSession, Task, TaskStatus
    from src.resources import current_session
    from src.schemas import SessionResource

    session = WizardSession()
    task = Task(name="Open task", status=TaskStatus.TODO)
    db_session.add(session)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(session)

    with patch("src.resources.get_session", _mock_session(db_session)):
        result = current_session()

    assert isinstance(result, SessionResource)
    assert result.session_id == session.id
    assert result.open_task_count == 1
    assert result.blocked_task_count == 0


def test_current_session_resource_none(db_session):
    from src.resources import current_session
    from src.schemas import SessionResource

    with patch("src.resources.get_session", _mock_session(db_session)):
        result = current_session()

    assert isinstance(result, SessionResource)
    assert result.session_id is None


def test_task_context_resource(db_session):
    from src.models import Task, TaskStatus, Note, NoteType
    from src.resources import task_context
    from src.schemas import TaskContextResource

    task = Task(name="Fix auth", status=TaskStatus.IN_PROGRESS, source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(note_type=NoteType.INVESTIGATION, content="Found root cause", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    with patch("src.resources.get_session", _mock_session(db_session)):
        result = task_context(task_id=task.id)

    assert isinstance(result, TaskContextResource)
    assert result.task.name == "Fix auth"
    assert len(result.notes) == 1
    assert result.notes[0].content == "Found root cause"


def test_config_resource(db_session):
    from src.resources import wizard_config
    from src.schemas import ConfigResource

    result = wizard_config()

    assert isinstance(result, ConfigResource)
    assert isinstance(result.jira_enabled, bool)
    assert isinstance(result.notion_enabled, bool)
    assert isinstance(result.scrubbing_enabled, bool)
    assert isinstance(result.database_path, str)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_resources.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.resources'`

- [ ] **Step 4: Implement resource handlers**

Create `src/resources.py`:

```python
from sqlmodel import col, select

from .database import get_session
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

_task_repo = TaskRepository()
_note_repo = NoteRepository()


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
            return SessionResource(session_id=None, open_task_count=0, blocked_task_count=0)
        return SessionResource(
            session_id=session.id,
            open_task_count=len(_task_repo.get_open_task_contexts(db)),
            blocked_task_count=len(_task_repo.get_blocked_task_contexts(db)),
        )


def open_tasks() -> OpenTasksResource:
    """All open tasks with status and priority."""
    with get_session() as db:
        return OpenTasksResource(tasks=_task_repo.get_open_task_contexts(db))


def blocked_tasks() -> BlockedTasksResource:
    """All blocked tasks."""
    with get_session() as db:
        return BlockedTasksResource(tasks=_task_repo.get_blocked_task_contexts(db))


def task_context(task_id: int) -> TaskContextResource:
    """Full task detail — metadata, notes, history."""
    with get_session() as db:
        task = _task_repo.get_by_id(db, task_id)
        task_ctx = _task_repo.build_task_context(db, task)
        notes = _note_repo.get_for_task(db, task_id=task.id, source_id=task.source_id)
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
    from .config import settings

    return ConfigResource(
        jira_enabled=bool(settings.jira.token),
        notion_enabled=bool(settings.notion.token),
        scrubbing_enabled=settings.scrubbing.enabled,
        database_path=settings.db,
    )


# ---------------------------------------------------------------------------
# Register resources with MCP
# ---------------------------------------------------------------------------

def _get_mcp():
    from .mcp_instance import mcp
    return mcp


_mcp = _get_mcp()
_mcp.resource("wizard://session/current")(current_session)
_mcp.resource("wizard://tasks/open")(open_tasks)
_mcp.resource("wizard://tasks/blocked")(blocked_tasks)
_mcp.resource("wizard://tasks/{task_id}/context")(task_context)
_mcp.resource("wizard://config")(wizard_config)
```

- [ ] **Step 5: Run resource tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_resources.py -x -v`
Expected: All resource tests pass

- [ ] **Step 6: Register resources in server.py**

Update `server.py`:

```python
from src.mcp_instance import mcp
import src.tools  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.tool decorators
import src.resources  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.resource decorators

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 7: Run all tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/schemas.py src/resources.py tests/test_resources.py server.py
git commit -m "feat: add FastMCP resource layer for session, tasks, and config

Resources expose read-only data via wizard:// URIs. Claude Code can pull
context on demand without invoking tools."
```

---

### Task 4: Tool Return Types

**Files:**
- Modify: `src/tools.py:132-457`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Write spike test for FastMCP Pydantic model serialization**

Add to `tests/test_tools.py` at the end:

```python
def test_fastmcp_serializes_pydantic_models():
    """Spike: verify FastMCP 3.2.0+ can serialize our response models without .model_dump()."""
    from fastmcp import FastMCP
    from src.schemas import SessionStartResponse, SourceSyncStatus

    test_mcp = FastMCP("test")

    @test_mcp.tool()
    def test_tool() -> SessionStartResponse:
        return SessionStartResponse(
            session_id=1,
            open_tasks=[],
            blocked_tasks=[],
            unsummarised_meetings=[],
            sync_results=[SourceSyncStatus(source="jira", ok=True)],
        )

    assert test_tool is not None
```

- [ ] **Step 2: Run spike test**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_tools.py::test_fastmcp_serializes_pydantic_models -x -v`
Expected: PASS

- [ ] **Step 3: Update all tool functions to return Pydantic models directly**

In `src/tools.py`:

1. Update the imports to include `TaskStartResponse`:

```python
from .schemas import (
    CreateTaskResponse,
    GetMeetingResponse,
    IngestMeetingResponse,
    SaveMeetingSummaryResponse,
    SaveNoteResponse,
    SessionEndResponse,
    SessionStartResponse,
    TaskStartResponse,
    UpdateTaskStatusResponse,
)
```

2. For each tool function, change `-> dict` to the actual return type and remove `.model_dump(mode="json")`:

- `session_start() -> dict` → `session_start() -> SessionStartResponse`
- `task_start(task_id: int) -> dict` → `task_start(task_id: int) -> TaskStartResponse`
- `save_note(...) -> dict` → `save_note(...) -> SaveNoteResponse`
- `update_task_status(...) -> dict` → `update_task_status(...) -> UpdateTaskStatusResponse`
- `get_meeting(meeting_id: int) -> dict` → `get_meeting(meeting_id: int) -> GetMeetingResponse`
- `save_meeting_summary(...) -> dict` → `save_meeting_summary(...) -> SaveMeetingSummaryResponse`
- `session_end(...) -> dict` → `session_end(...) -> SessionEndResponse`
- `ingest_meeting(...) -> dict` → `ingest_meeting(...) -> IngestMeetingResponse`
- `create_task(...) -> dict` → `create_task(...) -> CreateTaskResponse`

3. In each function, change `return XxxResponse(...).model_dump(mode="json")` to `return XxxResponse(...)`.

- [ ] **Step 4: Update test_tools.py assertions for Pydantic model returns**

In `tests/test_tools.py`:

1. Remove `import json` from the top (no longer needed).

2. Replace every `data = result if isinstance(result, dict) else json.loads(result)` pattern with direct attribute access on the result. Replace `data["field"]` with `result.field` and `data["nested"]["field"]` with `result.nested.field`.

Examples of key replacements across the file:

- `data["session_id"]` → `result.session_id`
- `data["open_tasks"]` → `result.open_tasks`
- `data["sync_results"]` → `result.sync_results`
- `data["sync_results"][0]["source"]` → `result.sync_results[0].source`
- `data["compounding"]` → `result.compounding`
- `data["prior_notes"]` → `result.prior_notes`
- `data["note_id"]` → `result.note_id`
- `data["new_status"]` → `result.new_status` (note: this will be `TaskStatus.DONE` enum, not `"done"` string)
- `data["jira_write_back"]["ok"]` → `result.jira_write_back.ok`
- `data["notion_write_back"]["ok"]` → `result.notion_write_back.ok`
- `data["meeting_id"]` → `result.meeting_id`
- `data["already_existed"]` → `result.already_existed`
- `data["task_id"]` → `result.task_id`

**Important:** In `test_update_task_status_persists_and_writebacks`, the assertion `data["new_status"] == "done"` must change to `result.new_status == TaskStatus.DONE` since it's now an enum, not a string.

3. In `test_compounding_loop_across_two_sessions`, replace all `s1_data`, `ts1_data`, `s2_data`, `ts2_data` with direct attribute access:

```python
        s1 = session_start()
        session_id = s1.session_id

        ts1 = task_start(task_id=task_id)
        assert ts1.compounding is False

        save_note(task_id=task_id, note_type="investigation", content="Found the root cause")
        update_task_status(task_id=task_id, new_status="in_progress")
        session_end(session_id=session_id, summary="Investigated auth bug")

        s2 = session_start()
        assert s2.session_id != session_id

        ts2 = task_start(task_id=task_id)
        assert ts2.compounding is True
        assert len(ts2.prior_notes) >= 1
        assert ts2.notes_by_type["investigation"] >= 1
```

- [ ] **Step 5: Run all tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/tools.py tests/test_tools.py
git commit -m "refactor: return Pydantic models directly from tool functions

Remove .model_dump(mode='json') boilerplate. FastMCP handles serialization."
```

---

### Task 5: Prompts

**Files:**
- Create: `src/prompts.py`
- Create: `tests/test_prompts.py`
- Modify: `server.py`

- [ ] **Step 1: Verify FastMCP Message import path**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -c "from fastmcp.prompts.base import Message; print('OK')"`

If that fails, try: `python -c "from fastmcp import Message; print('OK')"`

Use whichever import path works in the next step.

- [ ] **Step 2: Write failing tests for prompts**

Create `tests/test_prompts.py`:

```python
def test_session_triage_returns_messages():
    from src.prompts import session_triage

    result = session_triage(session_data="test session data")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert "test session data" in result[1].content


def test_task_investigation_returns_messages():
    from src.prompts import task_investigation

    result = task_investigation(task_data="test task data")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert "test task data" in result[1].content


def test_meeting_summarisation_returns_messages():
    from src.prompts import meeting_summarisation

    result = meeting_summarisation(meeting_data="test meeting data")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert "test meeting data" in result[1].content


def test_session_wrapup_returns_string():
    from src.prompts import session_wrapup

    result = session_wrapup()
    assert isinstance(result, str)
    assert len(result) > 0


def test_user_elicitation_returns_string():
    from src.prompts import user_elicitation

    result = user_elicitation()
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_prompts.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.prompts'`

- [ ] **Step 4: Implement prompts module**

Create `src/prompts.py` (adjust `Message` import based on Step 1):

```python
from fastmcp.prompts.base import Message


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


# ---------------------------------------------------------------------------
# Register prompts with MCP
# ---------------------------------------------------------------------------

def _get_mcp():
    from .mcp_instance import mcp
    return mcp


_mcp = _get_mcp()
_mcp.prompt()(session_triage)
_mcp.prompt()(task_investigation)
_mcp.prompt()(meeting_summarisation)
_mcp.prompt()(session_wrapup)
_mcp.prompt()(user_elicitation)
```

- [ ] **Step 5: Run prompt tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_prompts.py -x -v`
Expected: All prompt tests pass

- [ ] **Step 6: Register prompts in server.py**

Update `server.py`:

```python
from src.mcp_instance import mcp
import src.tools  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.tool decorators
import src.resources  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.resource decorators
import src.prompts  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.prompt decorators

if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 7: Run all tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/prompts.py tests/test_prompts.py server.py
git commit -m "feat: add FastMCP prompts for session triage, task investigation, and more

Five prompts guide Claude Code's reasoning: session_triage, task_investigation,
meeting_summarisation, session_wrapup, user_elicitation."
```

---

### Task 6: Context Integration

**Files:**
- Modify: `src/tools.py:132-151,301-330,333-386,389-433`
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Verify Context import path**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -c "from fastmcp import Context; from fastmcp.server.dependencies import CurrentContext; print('OK')"`

If `CurrentContext` isn't at that path, try: `python -c "from fastmcp.dependencies import CurrentContext; print('OK')"`

Use whichever import path works.

- [ ] **Step 2: Add Context imports to tools.py**

Add at the top of `src/tools.py`:

```python
from fastmcp import Context
from fastmcp.server.dependencies import CurrentContext
```

- [ ] **Step 3: Add Context to session_start**

Update `session_start` signature and body:

```python
def session_start(ctx: Context = CurrentContext()) -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    from .models import WizardSession

    with get_session() as db:
        ctx.info("Creating new session")
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        ctx.report_progress(1, 3)
        ctx.info("Syncing integrations")
        sync_results = _sync_service().sync_all(db)

        ctx.report_progress(2, 3)
        result = SessionStartResponse(
            session_id=session.id,
            open_tasks=_task_repo().get_open_task_contexts(db),
            blocked_tasks=_task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=_meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
        )
        ctx.report_progress(3, 3)
        return result
```

- [ ] **Step 4: Add Context to session_end**

```python
def session_end(session_id: int, summary: str, ctx: Context = CurrentContext()) -> SessionEndResponse:
```

Add `ctx.info("Saving session summary")` before the scrub call, and `ctx.info("Writing back to Notion")` before the write-back call.

- [ ] **Step 5: Add Context to ingest_meeting**

```python
def ingest_meeting(
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: str = "general",
    ctx: Context = CurrentContext(),
) -> IngestMeetingResponse:
```

Add `ctx.info("Scrubbing and storing meeting")` after entering the db context, and `ctx.info("Writing back to Notion")` before the write-back call.

- [ ] **Step 6: Add Context to create_task**

```python
def create_task(
    name: str,
    priority: str = "medium",
    category: str = "issue",
    source_id: str | None = None,
    source_url: str | None = None,
    meeting_id: int | None = None,
    ctx: Context = CurrentContext(),
) -> CreateTaskResponse:
```

Add `ctx.info("Creating task")` after entering the db context, and `ctx.info("Writing back to Notion")` before the write-back call.

- [ ] **Step 7: Add mock Context helper to test_tools.py**

Add at the top of `tests/test_tools.py`:

```python
def _mock_context():
    """Create a mock Context for testing tools that accept ctx parameter."""
    ctx = MagicMock()
    ctx.info = MagicMock()
    ctx.warning = MagicMock()
    ctx.report_progress = MagicMock()
    return ctx
```

- [ ] **Step 8: Pass mock Context to affected test calls**

Update every test that calls `session_start`, `session_end`, `ingest_meeting`, or `create_task` to pass `ctx=_mock_context()`.

For `session_start` calls: `session_start(ctx=_mock_context())`
For `session_end` calls: `session_end(session_id=..., summary=..., ctx=_mock_context())`
For `ingest_meeting` calls: `ingest_meeting(..., ctx=_mock_context())`
For `create_task` calls: `create_task(..., ctx=_mock_context())`

This affects: `test_session_start_creates_session`, `test_session_start_calls_sync`, `test_session_start_surfaces_sync_errors`, `test_session_end_saves_summary_note`, `test_ingest_meeting_creates_meeting`, `test_ingest_meeting_dedup_by_source_id`, `test_create_task_creates_and_links`, and `test_compounding_loop_across_two_sessions`.

Tools without Context (`task_start`, `save_note`, `update_task_status`, `get_meeting`, `save_meeting_summary`) remain unchanged.

- [ ] **Step 9: Run all tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 10: Commit**

```bash
git add src/tools.py tests/test_tools.py
git commit -m "feat: inject FastMCP Context for logging and progress in multi-step tools

session_start, session_end, ingest_meeting, create_task now use ctx.info()
and ctx.report_progress() for structured observability."
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Verify no import cycles**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -c "from src.mcp_instance import mcp; import src.tools; import src.resources; import src.prompts; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify server starts without errors**

Run: `cd /home/agntx/Documents/repos/personal/wizard && timeout 3 python server.py 2>&1 || true`
Expected: Server starts (may timeout after 3s — no import/startup errors)
