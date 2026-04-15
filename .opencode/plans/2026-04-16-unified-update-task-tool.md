# Unified update_task tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan step-by-step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-purpose `update_task_status` with a unified `update_task` tool that supports updating all mutable task fields atomically.

**Architecture:** Single tool with optional parameters. Each parameter maps to a task field. External writebacks are triggered selectively based on which fields changed. The deprecated `update_task_status` delegates to the new tool.

**Tech Stack:** Python 3.11+, SQLModel, FastMCP, pytest

---

## File Map

| File | Change |
|------|--------|
| `src/wizard/schemas.py` | Add `UpdateTaskRequest`, `UpdateTaskResponse` |
| `src/wizard/integrations.py` | Add `update_task_due_date()`, `update_task_priority()` to `NotionClient` |
| `src/wizard/services.py` | Add `push_task_due_date()`, `push_task_priority()` to `WriteBackService` |
| `src/wizard/tools.py` | Add `update_task()` function, deprecate `update_task_status()` |
| `tests/test_tools.py` | Add tests for `update_task` |
| `.opencode/plans/` | This plan |
| `docs/superpowers/specs/` | Design spec |

---

## Supported Fields

| Field | Type | Writeback | Notes |
|-------|------|-----------|-------|
| `status` | `TaskStatus` | Jira + Notion | Triggers `TaskState.on_status_changed()`. DONE elicits outcome. |
| `priority` | `TaskPriority` | Notion only | - |
| `due_date` | ISO 8601 string | Notion only | Parsed to datetime internally |
| `notion_id` | `str` | None | Local link only |
| `name` | `str` | None | Scrubbed before save |
| `source_url` | `str` | None | - |

---

## Task 1: Add Request/Response Schemas

**Files:**
- Modify: `src/wizard/schemas.py`

- [ ] **Step 1: Add `UpdateTaskRequest` class**

Append to `schemas.py`:

```python
class UpdateTaskRequest(BaseModel):
    """Optional fields — only provided (non-None) fields are updated.
    
    At least one field must be provided. Raises ToolError if empty.
    """
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: str | None = None  # ISO 8601 string, e.g. "2026-04-17T14:00:00Z"
    notion_id: str | None = None
    name: str | None = None
    source_url: str | None = None
```

- [ ] **Step 2: Add `UpdateTaskResponse` class**

Append to `schemas.py`:

```python
class UpdateTaskResponse(BaseModel):
    task_id: int
    updated_fields: list[str]
    status_writeback: WriteBackStatus | None = None  # Jira + Notion when status changed
    due_date_writeback: WriteBackStatus | None = None  # Notion when due_date changed
    priority_writeback: WriteBackStatus | None = None  # Notion when priority changed
    task_state_updated: bool = False
```

---

## Task 2: Add NotionClient Methods

**Files:**
- Modify: `src/wizard/integrations.py`

- [ ] **Step 1: Add `update_task_due_date` method**

Add to `NotionClient` class (after `update_task_status`):

```python
def update_task_due_date(self, page_id: str, due_date: str) -> bool:
    """Update due_date property on task page. due_date in ISO format."""
    client = self._require_client()
    try:
        client.pages.update(
            page_id=page_id,
            properties={self._schema.task_due_date: {"date": {"start": due_date}}},
        )
        return True
    except APIResponseError as e:
        logger.warning("Notion update_task_due_date failed: %s", e)
        return False
```

- [ ] **Step 2: Add `update_task_priority` method**

Add to `NotionClient` class:

```python
def update_task_priority(self, page_id: str, priority: str) -> bool:
    """Update priority select property on task page."""
    client = self._require_client()
    try:
        client.pages.update(
            page_id=page_id,
            properties={self._schema.task_priority: {"select": {"name": priority}}},
        )
        return True
    except APIResponseError as e:
        logger.warning("Notion update_task_priority failed: %s", e)
        return False
```

---

## Task 3: Add WriteBackService Methods

**Files:**
- Modify: `src/wizard/services.py`

- [ ] **Step 1: Add `push_task_due_date` method**

Add to `WriteBackService` class (after `push_task_status_to_notion`):

```python
def push_task_due_date(self, task: Task) -> WriteBackStatus:
    """Push due_date to Notion if task has notion_id."""
    if not task.notion_id:
        return WriteBackStatus(ok=False, error="Task has no notion_id")
    if not task.due_date:
        return WriteBackStatus(ok=False, error="Task has no due_date")
    due_date_iso = task.due_date.isoformat()
    return self._call(
        lambda: self._notion.update_task_due_date(task.notion_id, due_date_iso),
        "WriteBack push_task_due_date",
    )
```

- [ ] **Step 2: Add `push_task_priority` method**

Add to `WriteBackService` class:

```python
def push_task_priority(self, task: Task) -> WriteBackStatus:
    """Push priority to Notion if task has notion_id."""
    if not task.notion_id:
        return WriteBackStatus(ok=False, error="Task has no notion_id")
    priority_label = PriorityMapper.local_to_notion(task.priority)
    return self._call(
        lambda: self._notion.update_task_priority(task.notion_id, priority_label),
        "WriteBack push_task_priority",
    )
```

---

## Task 4: Implement `update_task` Tool

**Files:**
- Modify: `src/wizard/tools.py`

- [ ] **Step 1: Add `update_task` function signature**

Add to imports from schemas:
```python
from .schemas import (
    # ... existing imports ...
    UpdateTaskRequest,
    UpdateTaskResponse,
)
```

Add function (before `update_task_status`):

```python
async def update_task(
    ctx: Context,
    task_id: int,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_date: str | None = None,
    notion_id: str | None = None,
    name: str | None = None,
    source_url: str | None = None,
) -> UpdateTaskResponse:
    """Atomically update task fields. Only provided (non-None) fields are updated.
    
    Raises ToolError if no fields are provided or task not found.
    
    Writebacks:
    - status: Jira + Notion
    - due_date: Notion only
    - priority: Notion only
    """
    logger.info("update_task task_id=%d", task_id)
    
    # Require at least one field
    if all(v is None for v in [status, priority, due_date, notion_id, name, source_url]):
        raise ToolError("At least one field must be provided to update_task")
    
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "update_task", session_id=session_id)
            
            task = task_repo().get_by_id(db, task_id)
            
            updated_fields: list[str] = []
            
            # Apply field updates
            if status is not None:
                task.status = status
                updated_fields.append("status")
            
            if priority is not None:
                task.priority = priority
                updated_fields.append("priority")
            
            if due_date is not None:
                try:
                    due_date_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
                except ValueError:
                    raise ToolError(f"Invalid due_date format: {due_date}. Use ISO 8601.")
                task.due_date = due_date_dt
                updated_fields.append("due_date")
            
            if notion_id is not None:
                task.notion_id = notion_id
                updated_fields.append("notion_id")
            
            if name is not None:
                task.name = security().scrub(name).clean
                updated_fields.append("name")
            
            if source_url is not None:
                task.source_url = source_url
                updated_fields.append("source_url")
            
            db.add(task)
            db.flush()
            
            # Update TaskState if status changed
            task_state_updated = False
            if "status" in updated_fields:
                task_state_repo().on_status_changed(db, task.id)
                task_state_updated = True
            
            # Elicit outcome if status = DONE and task has notion_id
            if status == TaskStatus.DONE and task.notion_id:
                try:
                    result = await ctx.elicit(
                        "Task closed. What was the outcome? (1-2 sentences, or press Enter to skip)",
                        response_type=str,
                    )
                    if isinstance(result, AcceptedElicitation) and result.data:
                        scrubbed_outcome = security().scrub(result.data).clean
                        writeback().append_task_outcome(task, scrubbed_outcome)
                except Exception as e:
                    logger.debug("ctx.elicit unavailable for task outcome: %s", e)
            
            db.commit()
            
            # Writebacks
            status_writeback = None
            due_date_writeback = None
            priority_writeback = None
            
            if "status" in updated_fields:
                jira_wb = writeback().push_task_status(task)
                notion_wb = writeback().push_task_status_to_notion(task)
                status_writeback = WriteBackStatus(
                    ok=jira_wb.ok and notion_wb.ok,
                    error=", ".join(filter(None, [jira_wb.error, notion_wb.error])),
                    page_id=task.notion_id,
                )
            
            if "due_date" in updated_fields:
                due_date_writeback = writeback().push_task_due_date(task)
            
            if "priority" in updated_fields:
                priority_writeback = writeback().push_task_priority(task)
            
            return UpdateTaskResponse(
                task_id=task.id,
                updated_fields=updated_fields,
                status_writeback=status_writeback,
                due_date_writeback=due_date_writeback,
                priority_writeback=priority_writeback,
                task_state_updated=task_state_updated,
            )
    except ValueError as e:
        logger.warning("update_task failed: %s", e)
        raise ToolError(str(e)) from e
```

- [ ] **Step 2: Register the tool**

Add to the registration section at the bottom of `tools.py`:

```python
mcp.tool()(update_task)
```

---

## Task 5: Deprecate `update_task_status`

**Files:**
- Modify: `src/wizard/tools.py`
- Modify: `src/wizard/schemas.py`

- [ ] **Step 1: Update `update_task_status` docstring**

Modify the existing `update_task_status` function to add deprecation warning:

```python
async def update_task_status(
    ctx: Context, task_id: int, new_status: TaskStatus
) -> UpdateTaskStatusResponse:
    """Updates task status locally and attempts Jira and Notion write-back.
    
    .. deprecated::
        Use :func:`update_task` instead. This tool will be removed in a future version.
        Run ``wizard update`` to upgrade Wizard.
    """
    logger.warning(
        "update_task_status is deprecated. Use update_task instead. "
        "Run 'wizard update' to upgrade."
    )
    # ... rest of existing implementation ...
```

- [ ] **Step 2: Update response schema**

Add field to `UpdateTaskStatusResponse` in `schemas.py`:
```python
deprecation_warning: str | None = "Use update_task instead. Run 'wizard update' to upgrade."
```

Update the return in `update_task_status`:
```python
return UpdateTaskStatusResponse(
    task_id=task.id,
    new_status=task.status,
    jira_write_back=jira_wb,
    notion_write_back=notion_wb,
    task_state_updated=True,
    deprecation_warning="Use update_task instead. Run 'wizard update' to upgrade.",
)
```

---

## Task 6: Add Tests

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Test `update_task` updates single field**
- [ ] **Step 2: Test `update_task` updates multiple fields**
- [ ] **Step 3: Test `update_task` raises when no fields**
- [ ] **Step 4: Test `update_task` status change triggers writebacks**
- [ ] **Step 5: Test `update_task` DONE elicits outcome**
- [ ] **Step 6: Test `update_task` DONE without notion_id skips elicitation**
- [ ] **Step 7: Test `update_task` invalid due_date format**
- [ ] **Step 8: Test `update_task` name is scrubbed**
- [ ] **Step 9: Test `update_task_status` deprecation warning**

---

## Task 7: Update Documentation

**Files:**
- Modify: `~/.config/opencode/AGENTS.md`

- [ ] **Step 1: Add tool documentation**

Add `update_task` to the Wizard tools section with deprecation notice for `update_task_status`.

---

## Verification

- [ ] `pytest tests/test_tools.py -v`
- [ ] `ruff check src/wizard/`
- [ ] `pyright src/wizard/`
