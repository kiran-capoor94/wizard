# Pythonic & Pydantic Cleanup

**Date:** 2026-04-11
**Scope:** Internal refactoring across all `src/` modules. No external interface changes.
**Python:** 3.14+

## Problem

The codebase has accumulated non-Pythonic patterns: `dataclass` where Pydantic fits, legacy `typing` imports on a 3.14 project, manual global singletons, in-function imports repeated across 7+ tool functions, manual enum validation boilerplate, raw dict traversal for Notion API responses, and inconsistent `_` prefixing.

## Decision: Approach A (`@lru_cache` singletons)

Chosen over FastMCP lifespan (heavier diff, couples to DI model) and module-level instantiation (harder to mock in tests). `@lru_cache` gives clean Pythonic singletons with `cache_clear()` for test isolation.

Jira client stays httpx-based (no SDK swap).

---

## 1. Pydantic Migration

### `ScrubResult` (`security.py`)

`dataclass` to `BaseModel`. It's a pure data container; everything else already uses Pydantic.

```python
# Before
@dataclass
class ScrubResult:
    clean: str
    stubs_applied: Dict[str, str]
    was_modified: bool

# After
class ScrubResult(BaseModel):
    clean: str
    stubs_applied: dict[str, str]
    was_modified: bool
```

### `Message` (`prompts.py`)

`dataclass` to `BaseModel`. FastMCP accepts any object with `role` and `content` attributes.

```python
# Before
@dataclass
class Message:
    role: str
    content: str

# After
class Message(BaseModel):
    role: str
    content: str
```

## 2. Modern Typing (Python 3.14)

Applies across all files.

- `Dict` -> `dict`, `List` -> `list`, `Tuple` -> `tuple`, `Optional[X]` -> `X | None`
- Remove `from typing import Dict, List, Optional, Tuple`
- Remove `from __future__ import annotations` from `integrations.py` and `services.py`
- Remove `TYPE_CHECKING` guards — on 3.14, deferred annotation evaluation makes them unnecessary. Move guarded imports to top-level.
- `pyproject.toml`: `requires-python = ">=3.14"`

### Files affected

| File | What changes |
|---|---|
| `security.py` | `Dict`, `List`, `Optional`, `Tuple` -> builtins |
| `integrations.py` | Drop `__future__`, `TYPE_CHECKING`; top-level schema imports |
| `services.py` | Drop `__future__`, `TYPE_CHECKING`; top-level model imports |
| `repositories.py` | `Optional` -> `X \| None` |
| `schemas.py` | `Optional` -> `X \| None` |
| `models.py` | `Optional` -> `X \| None` |
| `pyproject.toml` | `requires-python` bump |

## 3. `@lru_cache` Singletons + Top-Level Imports

### `tools.py` — singletons

Replace 8 global-variable + `if None` guard blocks with `@lru_cache` functions. Drop `_` prefix.

```python
# Before
_jira_inst = None

def _jira_client():
    global _jira_inst
    if _jira_inst is None:
        from .config import settings
        from .integrations import JiraClient
        _jira_inst = JiraClient(...)
    return _jira_inst

# After
from functools import lru_cache

@lru_cache
def jira_client() -> JiraClient:
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
    )
```

All 8 singletons follow this pattern: `jira_client`, `notion_client`, `security`, `sync_service`, `writeback`, `task_repo`, `meeting_repo`, `note_repo`.

### `tools.py` — in-function imports

Move all `from .models import ...` and `from .schemas import ...` that appear inside tool function bodies to the module top. 7 functions have these. No circular dependency exists — verified by tracing the full import graph.

### `_get_mcp()` pattern

Appears in `tools.py:457`, `prompts.py:126`, `resources.py:89`. Each wraps a one-liner. Replace with direct top-level import:

```python
# Before
def _get_mcp():
    from .mcp_instance import mcp
    return mcp

_mcp = _get_mcp()

# After
from .mcp_instance import mcp
```

### `resources.py` — module-level repos

Lines 15-16 create `_task_repo = TaskRepository()` and `_note_repo = NoteRepository()`. These repos are stateless (no constructor args), so duplicate instances are harmless. Keep module-level instantiation, just drop the `_` prefix. Not worth introducing a coupling to `tools.py` or a `deps.py` module for stateless objects.

## 4. Enum-Typed Tool Params

Replace `str` params + manual validation with enum types directly in tool signatures. Pydantic + FastMCP handle coercion from string values.

```python
# Before
def create_task(name: str, priority: str = "medium", category: str = "issue", ...):
    valid_priorities = [p.value for p in TaskPriority]
    if priority not in valid_priorities:
        raise ValueError(...)
    valid_categories = [c.value for c in TaskCategory]
    if category not in valid_categories:
        raise ValueError(...)

# After
def create_task(
    name: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    category: TaskCategory = TaskCategory.ISSUE,
    ...
):
```

### Functions affected

| Function | Params changing from `str` to enum |
|---|---|
| `save_note` | `note_type: str` -> `note_type: NoteType` |
| `update_task_status` | `new_status: str` -> `new_status: TaskStatus` |
| `ingest_meeting` | `category: str` -> `category: MeetingCategory` |
| `create_task` | `priority: str` -> `TaskPriority`, `category: str` -> `TaskCategory` |

Confirm FastMCP exposes enum params as string values in the MCP tool schema before implementation. If it doesn't, keep string params with a thinner validation layer (single `Enum(value)` call, no manual list-building).

## 5. Notion Property Models

Replace 8 `_get_*` helper functions in `integrations.py` with Pydantic models that parse the Notion API property structure.

```python
class NotionPropertyValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

class NotionTitle(NotionPropertyValue):
    title: list[dict] = []

    @property
    def text(self) -> str | None:
        return self.title[0].get("plain_text") if self.title else None

class NotionSelect(NotionPropertyValue):
    select: dict | None = None

    @property
    def name(self) -> str | None:
        return self.select.get("name") if self.select else None

class NotionRichText(NotionPropertyValue):
    rich_text: list[dict] = []

    @property
    def text(self) -> str | None:
        return self.rich_text[0].get("plain_text") if self.rich_text else None

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

class NotionMultiSelect(NotionPropertyValue):
    multi_select: list[dict] = []

    @property
    def names(self) -> list[str]:
        return [item["name"] for item in self.multi_select if "name" in item]
```

Call sites become:

```python
# Before
name = _get_title(props, "Task")
status = _get_status(props, "Status")

# After
name = NotionTitle.model_validate(props.get("Task", {})).text
status = NotionStatus.model_validate(props.get("Status", {})).text
```

`_extract_jira_key` stays — it's URL regex, not Notion property parsing.

These models live in `schemas.py` alongside the existing Notion data models, or in a new `src/notion_models.py` if `schemas.py` grows too large. Decision: keep in `schemas.py` — they're small and directly related to the existing `NotionTaskData` / `NotionMeetingData` models.

## 6. `_` Prefix Cleanup

### Remove `_` from:

| Location | Examples |
|---|---|
| `tools.py` singleton functions | `_jira_client` -> `jira_client`, `_sync_service` -> `sync_service`, etc. |
| `integrations.py` constant | `_HTTPX_TIMEOUT` -> `HTTPX_TIMEOUT` |
| `mappers.py` lookup dicts | `_JIRA_STATUS_MAP` -> `JIRA_STATUS_MAP`, etc. (6 dicts) |

### Keep `_` on:

| Location | Reason |
|---|---|
| `repositories.py:_latest_note_subquery` | Implementation detail of the repository |
| `repositories.py:_PRIORITY_ORDER` | Internal query helper |
| `repositories.py:_task_context_from_row` | Internal row mapper |

Rule: `_` means "don't call this from outside this module." Constants and accessors that other modules use drop the prefix.

## Blast Radius

- **External interfaces:** Zero changes. MCP tool names, resource URIs, prompt names, and all response schemas stay identical.
- **Database:** No schema changes, no migration needed.
- **Dependencies:** No new packages. `requires-python` bump only.
- **Tests:** Will need updates for import paths (renamed functions) and may need `cache_clear()` calls in fixtures. No test logic changes.

## Files Touched

| File | Changes |
|---|---|
| `pyproject.toml` | `requires-python` bump |
| `src/security.py` | `ScrubResult` -> `BaseModel`, modern typing |
| `src/prompts.py` | `Message` -> `BaseModel`, top-level imports |
| `src/tools.py` | `@lru_cache` singletons, top-level imports, enum params, drop `_get_mcp` |
| `src/integrations.py` | Drop `__future__`/`TYPE_CHECKING`, Notion property models usage, `HTTPX_TIMEOUT` |
| `src/schemas.py` | Modern typing, Notion property models added |
| `src/services.py` | Drop `__future__`/`TYPE_CHECKING`, top-level imports |
| `src/repositories.py` | Modern typing |
| `src/models.py` | Modern typing |
| `src/resources.py` | Drop `_` from repo instances, top-level imports, drop `_get_mcp` |
| `src/mappers.py` | Drop `_` from dict names |
| `src/mcp_instance.py` | No changes |
| `src/database.py` | No changes |
| `tests/*` | Import path updates, `cache_clear()` in fixtures |
