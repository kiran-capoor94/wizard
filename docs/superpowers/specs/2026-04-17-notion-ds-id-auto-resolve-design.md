# Design: Auto-resolve Notion Data Source IDs from URLs

**Date:** 2026-04-17  
**Status:** Approved

## Problem

`_configure_notion` currently prompts:

```
Tasks data source ID (not the URL page ID — use the data_sources API field):
Meetings data source ID (not the URL page ID — use the data_sources API field):
```

Data source IDs are not visible anywhere in the Notion UI. Users can only obtain them via the API. This creates an unnecessary barrier — the user must run a separate API call, copy the UUID, and paste it back. In practice, users paste the URL page ID and get silent 404s.

## Goal

Accept full Notion database URLs during setup. Wizard extracts the page ID from the URL, calls the Notion API to resolve it to a data source ID, and saves the result — the user never sees or handles a data source ID.

## Approach: Resolve at prompt time

Prompt accepts a full URL. Resolution happens immediately after entry. On success, the data source ID is saved silently. On failure, the error is printed and the user is re-prompted without exiting setup.

## New Helper Functions (`src/wizard/cli/main.py`)

### `_resolve_notion_page_id(url: str) -> str`

Extracts the 32-character hex page ID from a Notion URL and formats it as a UUID.

Notion URL patterns:
```
https://www.notion.so/workspace/My-Tasks-abc123def456789012345678901234ab
https://www.notion.so/abc123def456789012345678901234ab
https://www.notion.so/My-Tasks-abc123def456789012345678901234ab?v=...
```

The page ID is always the last 32 contiguous hex characters in the URL path before any `?`. Extract with regex `[0-9a-f]{32}`, then format as `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

Raises `ValueError` if no 32-char hex ID is found in the URL.

### `_resolve_ds_id(client, page_id: str) -> str`

Calls `client.databases.retrieve(database_id=page_id)` and returns the first entry's `id` from the `data_sources` field.

```python
response = client.databases.retrieve(database_id=page_id)
sources = response.get("data_sources", [])
if not sources:
    raise ValueError("No data sources found for this database")
return sources[0]["id"]
```

Note: `databases.retrieve()` is used here specifically to get the `data_sources` field, not to read schema or properties — this is the documented use case and does not violate the CLAUDE.md rule against using it for schema access.

Raises `ValueError` with a descriptive message on failure.

## Updated `_configure_notion` Flow

The two existing prompts for `tasks_ds_id` and `meetings_ds_id` are replaced with URL prompts + inline resolution. Resolution retries on failure (re-prompts) rather than exiting setup.

```
  Notion integration
  token: set
  daily page ID: skipped

  Tasks database URL: https://notion.so/workspace/My-Tasks-abc123...
  → Resolving...  ok
  tasks database: set

  Meetings database URL: https://notion.so/workspace/Meetings-def456...
  → Resolving...  ok
  meetings database: set
```

On failure:
```
  Tasks database URL: https://notion.so/workspace/not-a-db
  → Resolving...  failed: No data sources found for this database. Paste the database URL from Notion.
  Tasks database URL: _
```

The resolution loop retries until success or the user presses Ctrl+C.

The Notion client (`NotionSdkClient(auth=token)`) is constructed once inside `_configure_notion`, before the URL prompts, so it can be reused for both tasks and meetings resolution.

## Files to Change

| File | Change |
|------|--------|
| `src/wizard/cli/main.py` | Add `_resolve_notion_page_id`, `_resolve_ds_id`; update `_configure_notion` to use URL prompts with inline resolution |
| `tests/test_cli.py` | Add tests for `_resolve_notion_page_id`, `_resolve_ds_id`, and the updated `_configure_notion` URL flow |

No other files change.

## What is NOT changing

- `_run_notion_discovery` — unchanged, still receives valid ds_ids from config
- `_configure_jira` — unchanged
- `configure --notion`, `configure --jira` — unchanged
- Config file format — `tasks_ds_id` and `meetings_ds_id` still store data source IDs

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| URL has no recognisable page ID | Print "Could not extract page ID from URL." and re-prompt |
| `databases.retrieve` returns no `data_sources` | Print "No data sources found for this database." and re-prompt |
| API error (auth, network) | Print error message and re-prompt |

## Success Criteria

- User pastes a full Notion URL and wizard saves the correct data source ID without user intervention
- Invalid URLs re-prompt cleanly without exiting setup
- `_resolve_notion_page_id` correctly handles all three Notion URL formats
- `_resolve_ds_id` correctly extracts the first data source ID
