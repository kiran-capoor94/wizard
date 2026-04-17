# Bug Fixes from Code Review

**Date:** 2026-04-17
**Scope:** 6 surgical fixes — no refactoring, no new abstractions

## Fix 1: PHONE regex misses +44 numbers

**File:** `src/wizard/security.py:20`
**Bug:** `\b` before `\+44` never fires because `+` is a non-word character.
All UK phone numbers starting with `+44` pass through unscrubbed.

**Fix:** Replace leading `\b` with `(?<!\w)` — a negative lookbehind that
matches the same positions as `\b` for the `0` branch but also matches
before `+` (where no word character precedes it).

```python
# Before
("PHONE", r"\b(\+44|0)[\d\s\-]{9,13}\b", "PHONE"),

# After
("PHONE", r"(?<!\w)(\+44|0)[\d\s\-]{9,13}\b", "PHONE"),
```

## Fix 2: SecretStr for API tokens

**Files:** `src/wizard/config.py`, `src/wizard/deps.py`,
`src/wizard/cli/doctor.py`, `src/wizard/resources.py`

**Bug:** `jira.token` and `notion.token` are plain `str`. Any
`model_dump()`, `repr()`, or error trace leaks raw tokens.

**Fix:** Use `pydantic.SecretStr`. Update all consumer sites.

### config.py

```python
from pydantic import SecretStr

class JiraSettings(BaseModel):
    token: SecretStr = SecretStr("")

class NotionSettings(BaseModel):
    token: SecretStr = SecretStr("")
```

### deps.py (lines 28, 37)

```python
token=settings.jira.token.get_secret_value(),
token=settings.notion.token.get_secret_value(),
```

### doctor.py (lines 83, 92)

```python
if s.notion.token.get_secret_value():
if s.jira.token.get_secret_value():
```

### resources.py (lines 117-118)

```python
jira_enabled=bool(settings.jira.token.get_secret_value()),
notion_enabled=bool(settings.notion.token.get_secret_value()),
```

## Fix 3: Hide token input in CLI prompts

**File:** `src/wizard/cli/main.py:212,281`

**Bug:** Notion and Jira token prompts display the token as the user types.

**Fix:** Add `hide_input=True` to both `typer.prompt()` calls.

```python
# Notion (line 212)
token = typer.prompt("  Notion integration token ...", hide_input=True)

# Jira (line 281)
token = typer.prompt("  API token ...", hide_input=True)
```

## Fix 4: Jira null transition ID

**File:** `src/wizard/integrations.py:98-109`

**Bug:** `_get_transition_id` can return `None`. The caller passes it
directly into `{"transition": {"id": None}}`, which Jira rejects with a
400. The error message is generic ("Jira update_task_status failed")
instead of specific.

**Fix:** Check for `None` before making the API call.

```python
def update_task_status(self, source_id: str, status: str) -> bool:
    client = self._require_client()
    transition_id = self._get_transition_id(source_id, status)
    if transition_id is None:
        logger.warning("No Jira transition found for status %r on %s", status, source_id)
        return False
    try:
        response = client.post(
            f"/issue/{source_id}/transitions",
            json={"transition": {"id": transition_id}},
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as e:
        logger.warning("Jira update_task_status failed: %s", e)
        return False
```

## Fix 5: doctor.py sqlite3 context manager

**File:** `src/wizard/cli/doctor.py:49`

**Bug:** `sqlite3.connect()` result is not wrapped in a context manager.
If `execute` raises, `conn.close()` is skipped and the connection leaks.

**Fix:** Use try/finally to guarantee `conn.close()`.

Note: `sqlite3.connect()` as a context manager only manages the
*transaction* (commit/rollback), not the connection lifetime. A
try/finally is the correct pattern here.

```python
conn = sqlite3.connect(str(db_path))
try:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
finally:
    conn.close()
```

## Fix 6: Closure consistency in WriteBackService

**File:** `src/wizard/services.py:231-250`

**Bug:** `push_task_due_date` and `push_task_priority` capture
`task.notion_id` by reference in lambdas. `push_task_status` and
`append_task_outcome` correctly capture to a local variable first.
Currently safe because `_call` invokes synchronously, but inconsistent
and fragile.

**Fix:** Capture `task.notion_id` to a local before the lambda.

```python
def push_task_due_date(self, task: Task) -> WriteBackStatus:
    if not task.notion_id:
        return WriteBackStatus(ok=False, error="Task has no notion_id")
    if not task.due_date:
        return WriteBackStatus(ok=False, error="Task has no due_date")
    notion_id = task.notion_id          # capture before lambda
    due_date_iso = task.due_date.isoformat()
    return self._call(
        lambda: self._notion.update_task_due_date(notion_id, due_date_iso),
        "WriteBack push_task_due_date",
    )

def push_task_priority(self, task: Task) -> WriteBackStatus:
    if not task.notion_id:
        return WriteBackStatus(ok=False, error="Task has no notion_id")
    notion_id = task.notion_id          # capture before lambda
    priority_label = PriorityMapper.local_to_notion(task.priority)
    return self._call(
        lambda: self._notion.update_task_priority(notion_id, priority_label),
        "WriteBack push_task_priority",
    )
```

## Testing

- Run `uv run pytest` after all fixes to confirm no regressions.
- Fix 1 should be verified with a manual test:
  `SecurityService().scrub("call +44 7700 900000")` should produce
  `[PHONE_1]` in the output.
- Fix 2 may require test updates if any tests check `settings.jira.token`
  as a plain string.
