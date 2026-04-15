# Unified update_task tool — Design Spec

**Date:** 2026-04-16
**Status:** Draft

## Context

Wizard currently has a single-purpose `update_task_status` tool that atomically updates task status and writebacks to Jira and Notion. Users need to update other task fields (due_date, notion_id, priority) without triggering full external syncs. This spec designs a unified `update_task` tool that handles all mutable fields atomically while maintaining backward compatibility.

## Goals

1. **Unified interface** — single tool for all task field updates
2. **Atomic updates** — all-or-nothing within a single DB transaction
3. **Selective writebacks** — only update external systems when relevant fields change
4. **Backward compatibility** — deprecate `update_task_status` without breaking existing callers
5. **Type safety** — Pydantic schemas for request/response validation

## Supported Fields

| Field | Type | External Writeback | Special Behavior |
|-------|------|-------------------|------------------|
| `status` | `TaskStatus` | Jira + Notion | Triggers `TaskState.on_status_changed()`. DONE elicits outcome. |
| `priority` | `TaskPriority` | Notion only | - |
| `due_date` | ISO 8601 string | Notion only | Parsed to datetime internally |
| `notion_id` | `str` | None | Local link only |
| `name` | `str` | None | Scrubbed for PII before save |
| `source_url` | `str` | None | - |

## Request/Response Schema

### UpdateTaskRequest

```python
class UpdateTaskRequest(BaseModel):
    """All fields optional — only provided (non-None) fields are updated."""
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: str | None = None  # ISO 8601 string
    notion_id: str | None = None
    name: str | None = None
    source_url: str | None = None
```

### UpdateTaskResponse

```python
class UpdateTaskResponse(BaseModel):
    task_id: int
    updated_fields: list[str]  # Which fields were actually changed
    status_writeback: WriteBackStatus | None = None  # Jira + Notion for status
    due_date_writeback: WriteBackStatus | None = None  # Notion for due_date
    priority_writeback: WriteBackStatus | None = None  # Notion for priority
    task_state_updated: bool = False
```

## Behavior

### Required Fields

- `task_id` (required): The task to update
- At least one field must be provided (ToolError if none)

### Atomicity

All field updates happen within a single DB transaction. If any step fails, the entire operation rolls back.

### Writeback Strategy

| Field Changed | Jira | Notion |
|---------------|------|--------|
| status | Yes (if task has `source_id`) | Yes (if task has `notion_id`) |
| priority | No | Yes (if task has `notion_id`) |
| due_date | No | Yes (if task has `notion_id`) |
| notion_id | No | No |
| name | No | No |
| source_url | No | No |

### TaskState Updates

Only `status` changes trigger `TaskState.on_status_changed()`. This is consistent with the existing behavior in `update_task_status`.

### Outcome Elicitation

When `status=DONE` and task has `notion_id`:
1. Elicit outcome text from user
2. Scrub for PII
3. Append as paragraph to Notion page via `writeback().append_task_outcome()`

This matches existing behavior in `update_task_status`.

## Deprecation of update_task_status

The existing `update_task_status` tool is deprecated:

1. **Logging**: `logger.warning()` with deprecation message on every call
2. **Response**: `UpdateTaskStatusResponse` gains `deprecation_warning` field
3. **Timeline**: No removal date — user prompted to run `wizard update` when they use it

### Deprecation Message

```
update_task_status is deprecated. Use update_task instead. Run 'wizard update' to upgrade.
```

## Due Date Format

Due dates are accepted as ISO 8601 strings:
- `"2026-04-17T14:00:00Z"` — UTC
- `"2026-04-17T14:00:00+00:00"` — UTC with explicit offset
- `"2026-04-17"` — date only (time defaults to 00:00:00)

Parsed using `datetime.fromisoformat()` with `Z` → `+00:00` normalization.

Invalid formats raise `ToolError` with clear message.

## Error Handling

| Error | Behavior |
|-------|----------|
| Task not found | ToolError with "Task N not found" |
| No fields provided | ToolError with "At least one field must be provided" |
| Invalid due_date format | ToolError with "Invalid due_date format: X. Use ISO 8601." |
| Writeback failure | Logged, included in response, non-fatal |
| Elicit unavailable | Silently skipped (existing behavior) |

## NotionClient Additions

### update_task_due_date

```python
def update_task_due_date(self, page_id: str, due_date: str) -> bool:
    """Update due_date property on task page. due_date in ISO format."""
```

### update_task_priority

```python
def update_task_priority(self, page_id: str, priority: str) -> bool:
    """Update priority select property on task page."""
```

Both methods follow the existing pattern in `NotionClient`:
- Use `self._require_client()` for token check
- Return `bool` (True = success)
- Log warnings on `APIResponseError`

## WriteBackService Additions

### push_task_due_date

```python
def push_task_due_date(self, task: Task) -> WriteBackStatus:
    """Push due_date to Notion if task has notion_id."""
```

### push_task_priority

```python
def push_task_priority(self, task: Task) -> WriteBackStatus:
    """Push priority to Notion if task has notion_id."""
```

Both methods:
- Check for `notion_id` before calling NotionClient
- Return `WriteBackStatus` with appropriate error if missing `notion_id`
- Use `PriorityMapper.local_to_notion()` for priority conversion

## Testing Strategy

### Unit Tests

| Test | Description |
|------|-------------|
| `test_update_task_updates_single_field` | Verify single field update works |
| `test_update_task_updates_multiple_fields` | Verify multiple fields update atomically |
| `test_update_task_raises_when_no_fields` | Verify ToolError when no fields provided |
| `test_update_task_status_triggers_writebacks` | Verify Jira + Notion writebacks for status |
| `test_update_task_done_elicits_outcome` | Verify elicitation when status=DONE |
| `test_update_task_done_without_notion_id_skips_elicit` | Verify no elicitation without notion_id |
| `test_update_task_invalid_due_date_format` | Verify ToolError on bad format |
| `test_update_task_name_is_scrubbed` | Verify PII scrubbing on name |
| `test_update_task_status_deprecated` | Verify deprecation warning logged |

### Integration Points

- `WriteBackService.push_task_due_date` — tested via `update_task` tests
- `WriteBackService.push_task_priority` — tested via `update_task` tests
- `NotionClient.update_task_due_date` — mocked in unit tests
- `NotionClient.update_task_priority` — mocked in unit tests
- `TaskState.on_status_changed` — verified via TaskState assertions

## Files Changed

| File | Change |
|------|--------|
| `src/wizard/schemas.py` | Add `UpdateTaskRequest`, `UpdateTaskResponse`, update `UpdateTaskStatusResponse` |
| `src/wizard/integrations.py` | Add `update_task_due_date()`, `update_task_priority()` |
| `src/wizard/services.py` | Add `push_task_due_date()`, `push_task_priority()` |
| `src/wizard/tools.py` | Add `update_task()`, deprecate `update_task_status()` |
| `tests/test_tools.py` | Add tests for `update_task` |
| `docs/superpowers/plans/` | Implementation plan |
| `docs/superpowers/specs/` | This design spec |

## Open Questions

None — all decisions made in planning phase.
