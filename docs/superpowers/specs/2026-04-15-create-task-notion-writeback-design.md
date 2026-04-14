# create_task Notion Writeback Fix

**Date:** 2026-04-15
**Branch:** development

## Context

`create_task` always fails to write back to Notion. The symptom is `notion_write_back.error = "Notion create_task_page returned no page ID"`. Two bugs compound each other:

1. `create_task_page` and `create_meeting_page` hardcode Notion property names (`"Task"`, `"Status"`, `"Priority"`, etc.) instead of reading from `self._schema`. `fetch_tasks` and `fetch_meetings` already use `self._schema` correctly — the write path is inconsistent with the read path. If the user's Notion DB uses any name other than the defaults, every write silently fails.

2. Both methods catch `APIResponseError` internally and return `None`. The caller sees `None` and emits the generic "no page ID" message. The real Notion error (wrong property name, invalid status option, missing required field) is only in the logs.

The `_check_notion_schema` doctor check compounds this: it only validates that config strings are non-empty, not that they match the live Notion DB.

## Design

### 1. Fix `create_task_page` (`src/wizard/integrations.py`)

Replace hardcoded property names with schema fields:

| Hardcoded | Schema field |
|---|---|
| `"Task"` | `self._schema.task_name` |
| `"Status"` | `self._schema.task_status` |
| `"Priority"` | `self._schema.task_priority` |
| `"Jira"` | `self._schema.task_jira_key` |
| `"Due date"` | `self._schema.task_due_date` |

Remove the internal `except APIResponseError` block. `push_task_to_notion` already has `except Exception` → `WriteBackStatus(ok=False, error=str(e))`. The real Notion error will surface there.

### 2. Fix `create_meeting_page` (`src/wizard/integrations.py`)

Same treatment for meeting properties that have schema fields:

| Hardcoded | Schema field |
|---|---|
| `"Meeting name"` | `self._schema.meeting_title` |
| `"Krisp URL"` | `self._schema.meeting_url` |
| `"Summary"` | `self._schema.meeting_summary` |

`"Category"` has no `NotionSchemaSettings` field — it stays hardcoded as `"Category"` (`multi_select`).

Remove internal `except APIResponseError` — propagate to `push_meeting_to_notion`.

### 3. Enhance `_check_notion_schema` (`src/wizard/cli/main.py`)

Replace the current body (non-empty config check) with a live Notion validation:

1. Load settings; if `tasks_db_id` or `meetings_db_id` is empty, fail fast with "run wizard setup"
2. Instantiate `NotionSdkClient(auth=token)`
3. Call `fetch_db_properties(client, tasks_db_id)` and `fetch_db_properties(client, meetings_db_id)` from `notion_discovery`
4. Validate each schema field against the live DB:

**Tasks DB:**
| Schema field | Expected Notion type |
|---|---|
| `task_name` | `title` |
| `task_status` | `status` |
| `task_priority` | `select` |
| `task_due_date` | `date` |
| `task_jira_key` | `url` |

**Meetings DB:**
| Field | Expected Notion type | Source |
|---|---|---|
| `meeting_title` | `title` | `NotionSchemaSettings` |
| `meeting_date` | `date` | `NotionSchemaSettings` |
| `meeting_url` | `url` | `NotionSchemaSettings` |
| `meeting_summary` | `rich_text` | `NotionSchemaSettings` |
| `"Category"` | `multi_select` | hardcoded |

5. Collect all mismatches (missing properties, wrong types). If any: `return False, "Tasks DB: <details>; Meetings DB: <details>"`
6. On pass: `return True, "Notion schema matches live DB"`

The check is at index 8 in `_DOCTOR_CHECK_NAMES` and is already skipped when the Notion token check fails — no structural change needed.

## Files Modified

- `src/wizard/integrations.py` — `create_task_page`, `create_meeting_page`
- `src/wizard/cli/main.py` — `_check_notion_schema`

## Tests

**`tests/test_integrations.py`:**
- `create_task_page` uses `schema.task_name` as property key (not hardcoded `"Task"`)
- `create_task_page` propagates `APIResponseError` instead of swallowing it
- `create_meeting_page` uses `schema.meeting_title` as property key
- `create_meeting_page` propagates `APIResponseError`

**`tests/test_cli.py`** (doctor check):
- Both DBs match schema → `(True, "Notion schema matches live DB")`
- Task property missing from live DB → `(False, "Tasks DB: ...")`
- Property exists but wrong type → `(False, "Tasks DB: ...")`

## Verification

1. `uv run pytest tests/test_integrations.py tests/test_cli.py -x` — all pass
2. `wizard doctor` with a misconfigured Notion DB → check fails with a clear message listing the bad properties
3. `wizard doctor` with a correctly configured DB → check passes
4. `mcp__wizard__create_task` call → task created in DB and in Notion, `notion_write_back.ok = true`
