# Daily Page Lifecycle Design

## Context

The wizard MCP server writes session summaries to a Notion "daily page" via
`session_end`. Currently `daily_page_id` is a static config value that must be
manually updated each day. This is fragile — the config goes stale, the ID
format can be wrong (slug vs UUID), and there's no mechanism to create or
archive daily pages.

**Goal:** `session_start` automatically ensures today's daily page exists under
the SISU Work parent page, archives any older daily pages, and makes the
resolved page ID available to `session_end` for write-back.

## Design

### Title Convention

Daily pages use the format `"Friday 11 April 2026"` (strftime `"%A %-d %B %Y"`).
This is the search key for finding existing pages and the title for new ones.

### Config Changes

**`NotionSettings` (`src/config.py`):**
- Remove `daily_page_id: str`
- Add `sisu_work_page_id: str` — the UUID of the parent page where daily pages
  live

**`config.json`:**
- Replace `"daily_page_id": "..."` with `"sisu_work_page_id": "<UUID>"`

### NotionClient Changes (`src/integrations.py`)

**Constructor:** Remove `daily_page_id` parameter, add `sisu_work_page_id`.

**New methods:**

`find_daily_page(title: str) -> str | None`
: Search Notion for a page with the given title. Filter results to pages whose
  parent matches `sisu_work_page_id`. Return the page ID if found, None
  otherwise. Uses the Notion search API.

`create_daily_page(title: str) -> str`
: Create a child page under `sisu_work_page_id` with the given title and an
  empty `"Session Summary"` rich_text property. Return the new page ID. Raise
  on failure (this is not a soft-fail path — if we can't create the page, the
  session should know).

`archive_page(page_id: str) -> bool`
: Call `pages.update(page_id, archived=True)`. Return True on success, False
  on API error. Used to archive stale daily pages.

`find_stale_daily_pages(today_title: str) -> list[str]`
: Search Notion for non-archived child pages of `sisu_work_page_id` that are
  NOT titled `today_title`. Return their page IDs. These are candidates for
  archiving.

**Existing method changes:**

`update_daily_page(page_id: str, summary: str) -> bool`
: Now takes `page_id` as a parameter instead of reading from `self._daily_page_id`.
  The caller provides the session's resolved page ID.

### Model Changes (`src/models.py`)

Add `daily_page_id: str | None = None` column to `WizardSession`. This stores
the Notion page ID resolved at session start so that `session_end` can write to
it without re-resolving.

**Migration:** Alembic migration adds nullable `daily_page_id` column to
`wizard_sessions`.

### Service Changes (`src/services.py`)

**`WriteBackService.push_session_summary`:**
- Change from reading `self._notion._daily_page_id` (encapsulation violation
  waiting to happen) to accepting the page ID from the session
- Signature: `push_session_summary(self, session: WizardSession) -> WriteBackStatus`
  (unchanged, but now reads `session.daily_page_id` instead of using config)
- If `session.daily_page_id` is None, return
  `WriteBackStatus(ok=False, error="No daily page ID on session")`

### Orchestration (`src/tools.py`)

**`session_start`:** After sync, call a new `ensure_daily_page` helper:

```
ensure_daily_page(notion_client) -> DailyPageResult:
    title = today's date in title format
    page_id = notion.find_daily_page(title)
    if not page_id:
        page_id = notion.create_daily_page(title)
    stale = notion.find_stale_daily_pages(title)
    for stale_id in stale:
        notion.archive_page(stale_id)
    return DailyPageResult(page_id=page_id, created=..., archived_count=len(stale))
```

Store the `page_id` on the `WizardSession` record. Include the result in
`SessionStartResponse` so the user can see what happened.

**`session_end`:** `push_session_summary` now uses `session.daily_page_id`.
If it's None (session started before this feature), fall back to error.

### Dependency Changes (`src/deps.py`)

Update `NotionClient` construction: pass `sisu_work_page_id` instead of
`daily_page_id`.

### Schema Changes (`src/schemas.py`)

Add `DailyPageResult` to `SessionStartResponse`:
```
class DailyPageResult(BaseModel):
    page_id: str
    created: bool
    archived_count: int

class SessionStartResponse(BaseModel):
    # ... existing fields ...
    daily_page: DailyPageResult | None = None
```

### Error Handling

- `find_daily_page` returns None on not-found or API error (soft fail)
- `create_daily_page` raises on failure (hard fail — session start should
  surface this clearly)
- `archive_page` returns False on failure (soft fail — archiving old pages
  is best-effort)
- `find_stale_daily_pages` returns empty list on failure (soft fail)
- `update_daily_page` returns False on failure (existing behavior)

### Files Modified

| File | Change |
|------|--------|
| `src/config.py` | Remove `daily_page_id`, add `sisu_work_page_id` |
| `config.json` | Replace `daily_page_id` with `sisu_work_page_id` |
| `src/integrations.py` | Update `NotionClient` constructor, add 4 new methods, modify `update_daily_page` signature |
| `src/models.py` | Add `daily_page_id` to `WizardSession` |
| `src/schemas.py` | Add `DailyPageResult`, update `SessionStartResponse` |
| `src/tools.py` | Add `ensure_daily_page` helper, update `session_start` and `session_end` |
| `src/services.py` | Update `push_session_summary` to use `session.daily_page_id` |
| `src/deps.py` | Update `NotionClient` construction |
| `alembic/versions/` | New migration for `daily_page_id` column |
| `tests/test_integrations.py` | Tests for 4 new NotionClient methods |
| `tests/test_tools.py` | Update session_start/session_end tests |
| `tests/test_services.py` | Update push_session_summary tests |
| `tests/test_config.py` | Update config tests |

### Verification

1. Run `pytest` — all tests pass
2. Start the server, call `session_start` — verify daily page is created in
   Notion under SISU Work with today's title
3. Call `session_end` — verify session summary is written to the daily page
4. Start a second session on the same day — verify it finds the existing page
   (no duplicate)
5. Manually create a fake "yesterday" page, start a session — verify the old
   page is archived
