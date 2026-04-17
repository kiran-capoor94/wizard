# Review Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 bugs identified in the full-repo code review — phone scrubbing, token security, hidden input, Jira null transition, sqlite3 leak, closure capture.

**Architecture:** Surgical fixes in 6 files. No new modules, no refactoring. One new dependency (`phonenumbers`). The SecretStr change touches 4 files but each change is 1-2 lines.

**Tech Stack:** Python 3.14, Pydantic SecretStr, Google phonenumbers library

---

### Task 1: Add `phonenumbers` dependency

**Files:**
- Modify: `pyproject.toml:8-17`

- [ ] **Step 1: Add phonenumbers to dependencies**

In `pyproject.toml`, add `"phonenumbers>=8.13"` to the `dependencies` list:

```toml
dependencies = [
    "alembic>=1.18.4",
    "fastmcp[tasks]>=3.2.0",
    "httpx>=0.27",
    "notion-client>=3.0",
    "phonenumbers>=8.13",
    "pydantic-settings>=2.0",
    "sqlmodel>=0.0.38",
    "tomli-w>=1.0.0",
    "typer>=0.12.0",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `uv sync`
Expected: Resolves and installs `phonenumbers`.

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "import phonenumbers; print(phonenumbers.__version__)"`
Expected: Prints a version number (e.g. `8.13.x`).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add phonenumbers library for phone number scrubbing"
```

---

### Task 2: Replace PHONE regex with phonenumbers library

**Files:**
- Modify: `src/wizard/security.py`
- Modify: `tests/test_security.py`

- [ ] **Step 1: Write failing tests for phone number scrubbing**

Add these tests to the end of `tests/test_security.py`:

```python
def test_uk_phone_with_plus44_is_redacted():
    svc = SecurityService()
    result = svc.scrub("Call +44 7700 900000 for help")
    assert "[PHONE_1]" in result.clean
    assert "+44 7700 900000" not in result.clean
    assert result.was_modified is True


def test_uk_local_phone_is_redacted():
    svc = SecurityService()
    result = svc.scrub("Call 07700 900000 for help")
    assert "[PHONE_1]" in result.clean
    assert "07700 900000" not in result.clean


def test_us_phone_is_redacted():
    svc = SecurityService()
    result = svc.scrub("Call +1 (555) 123-4567 today")
    assert "[PHONE_1]" in result.clean
    assert "+1 (555) 123-4567" not in result.clean


def test_multiple_phones_get_indexed_stubs():
    svc = SecurityService()
    result = svc.scrub("A: +44 7700 900000 B: +1 555 123 4567")
    assert "[PHONE_1]" in result.clean
    assert "[PHONE_2]" in result.clean


def test_phone_allowlist_skips_match():
    svc = SecurityService(allowlist=[r"\+44 7700 900000"])
    result = svc.scrub("Call +44 7700 900000 for help")
    assert "+44 7700 900000" in result.clean
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_security.py -v -k "phone"`
Expected: All 5 new phone tests FAIL (the +44 and US tests fail because the current regex misses them).

- [ ] **Step 3: Replace PHONE regex with phonenumbers in security.py**

Replace the entire content of `src/wizard/security.py` with:

```python
import logging
import re

import phonenumbers
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ScrubResult(BaseModel):
    clean: str
    original_to_stub: dict[str, str]
    was_modified: bool


class SecurityService:
    PATTERNS: list[tuple[str, str, str]] = [
        ("NHS_ID", r"\b\d{3}\s\d{3}\s\d{4}\b", "NHS_ID"),
        ("NI_NUMBER", r"\b[A-Z]{2}\d{6}[A-D]\b", "NI_NUMBER"),
        ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "EMAIL"),
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

    def _scrub_phones(
        self,
        text: str,
        original_to_stub: dict[str, str],
        counters: dict[str, int],
    ) -> str:
        for match in phonenumbers.PhoneNumberMatcher(text, "GB"):
            raw = match.raw_string
            if any(p.search(raw) for p in self._allowlist_patterns):
                continue
            if raw in original_to_stub:
                continue
            counters["PHONE"] = counters.get("PHONE", 0) + 1
            stub = f"[PHONE_{counters['PHONE']}]"
            original_to_stub[raw] = stub
        # Replace longest matches first to avoid partial substitutions
        for original, stub in sorted(
            original_to_stub.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if stub.startswith("[PHONE_"):
                text = text.replace(original, stub)
        return text

    def scrub(self, content: str) -> ScrubResult:
        if not self._enabled:
            return ScrubResult(clean=content, original_to_stub={}, was_modified=False)
        clean = content
        original_to_stub: dict[str, str] = {}
        counters: dict[str, int] = {}

        for _name, pattern, prefix in self.PATTERNS:

            def replace(m: re.Match, _prefix: str = prefix) -> str:
                matched = m.group(0)
                if any(p.search(matched) for p in self._allowlist_patterns):
                    return matched
                if matched in original_to_stub:
                    return original_to_stub[matched]
                counters[_prefix] = counters.get(_prefix, 0) + 1
                stub = f"[{_prefix}_{counters[_prefix]}]"
                original_to_stub[matched] = stub
                return stub

            clean = re.sub(pattern, replace, clean)

        clean = self._scrub_phones(clean, original_to_stub, counters)

        if original_to_stub:
            logger.info(
                "PII scrubbed: %d substitution(s) across patterns",
                len(original_to_stub),
            )
        return ScrubResult(
            clean=clean,
            original_to_stub=original_to_stub,
            was_modified=clean != content,
        )
```

Key changes:
- Removed the `("PHONE", ...)` tuple from `PATTERNS`.
- Added `import phonenumbers` at the top.
- Added `_scrub_phones` method using `PhoneNumberMatcher` with default region `"GB"`.
- Called `_scrub_phones` after the regex loop in `scrub()`.

- [ ] **Step 4: Run all security tests**

Run: `uv run pytest tests/test_security.py -v`
Expected: All tests PASS (existing + new phone tests).

- [ ] **Step 5: Commit**

```bash
git add src/wizard/security.py tests/test_security.py
git commit -m "fix: replace PHONE regex with phonenumbers library

The \\b word boundary before \\+44 never matched, so all +44 numbers
passed through unscrubbed. phonenumbers handles all countries."
```

---

### Task 3: SecretStr for API tokens

**Files:**
- Modify: `src/wizard/config.py:7,39,61`
- Modify: `src/wizard/deps.py:28,37`
- Modify: `src/wizard/cli/doctor.py:83,92,166,169`
- Modify: `src/wizard/resources.py:117-118`
- Modify: `tests/test_config.py:14,45`

- [ ] **Step 1: Write failing test for SecretStr**

Add this test to the end of `tests/test_config.py`:

```python
def test_token_is_secret_str():
    from pydantic import SecretStr
    from wizard.config import JiraSettings, NotionSettings

    j = JiraSettings()
    n = NotionSettings()
    assert isinstance(j.token, SecretStr)
    assert isinstance(n.token, SecretStr)
    assert j.token.get_secret_value() == ""
    assert n.token.get_secret_value() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_token_is_secret_str -v`
Expected: FAIL — `token` is currently a plain `str`, not `SecretStr`.

- [ ] **Step 3: Change token fields to SecretStr in config.py**

In `src/wizard/config.py`, add `SecretStr` to the pydantic import on line 7:

```python
from pydantic import BaseModel, Field, SecretStr
```

Change `JiraSettings.token` (line 39):

```python
    token: SecretStr = SecretStr("")
```

Change `NotionSettings.token` (line 61):

```python
    token: SecretStr = SecretStr("")
```

- [ ] **Step 4: Update deps.py to call get_secret_value()**

In `src/wizard/deps.py`, change line 28:

```python
        token=settings.jira.token.get_secret_value(),
```

Change line 37:

```python
        token=settings.notion.token.get_secret_value(),
```

- [ ] **Step 5: Update doctor.py to call get_secret_value()**

In `src/wizard/cli/doctor.py`, change line 83:

```python
    if s.notion.token.get_secret_value():
```

Change line 92:

```python
    if s.jira.token.get_secret_value():
```

Change line 166:

```python
    if not notion.token.get_secret_value() or not notion.tasks_ds_id or not notion.meetings_ds_id:
```

Change line 169:

```python
    client = NotionSdkClient(auth=notion.token.get_secret_value())
```

- [ ] **Step 6: Update resources.py to call get_secret_value()**

In `src/wizard/resources.py`, change lines 117-118:

```python
                    jira_enabled=bool(settings.jira.token.get_secret_value()),
                    notion_enabled=bool(settings.notion.token.get_secret_value()),
```

- [ ] **Step 7: Update existing config tests for SecretStr**

In `tests/test_config.py`, change line 14 from:

```python
    assert settings.jira.token == ""
```

to:

```python
    assert settings.jira.token.get_secret_value() == ""
```

Change line 45 from:

```python
    assert settings.jira.token == "tok"
```

to:

```python
    assert settings.jira.token.get_secret_value() == "tok"
```

- [ ] **Step 8: Run all config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: All tests PASS.

- [ ] **Step 9: Run full test suite to check for other breakage**

Run: `uv run pytest -v`
Expected: All tests PASS. If any test compares `.token` as a plain string, it will fail and need the same `.get_secret_value()` fix.

- [ ] **Step 10: Commit**

```bash
git add src/wizard/config.py src/wizard/deps.py src/wizard/cli/doctor.py src/wizard/resources.py tests/test_config.py
git commit -m "fix: use SecretStr for API tokens to prevent accidental leakage

model_dump(), repr(), and error traces no longer expose raw tokens.
All consumer sites updated to call .get_secret_value()."
```

---

### Task 4: Hide token input in CLI prompts

**Files:**
- Modify: `src/wizard/cli/main.py:212,281`

- [ ] **Step 1: Add hide_input=True to Notion token prompt**

In `src/wizard/cli/main.py`, change line 212 from:

```python
    token = typer.prompt("  Notion integration token (notion.so/profile/integrations)")
```

to:

```python
    token = typer.prompt("  Notion integration token (notion.so/profile/integrations)", hide_input=True)
```

- [ ] **Step 2: Add hide_input=True to Jira token prompt**

In `src/wizard/cli/main.py`, change line 281 from:

```python
    token = typer.prompt("  API token (id.atlassian.com/manage-profile/security/api-tokens)")
```

to:

```python
    token = typer.prompt("  API token (id.atlassian.com/manage-profile/security/api-tokens)", hide_input=True)
```

- [ ] **Step 3: Commit**

```bash
git add src/wizard/cli/main.py
git commit -m "fix: hide token input during CLI configuration prompts"
```

---

### Task 5: Guard against null Jira transition ID

**Files:**
- Modify: `src/wizard/integrations.py:98-109`
- Modify: `tests/test_integrations.py`

- [ ] **Step 1: Write failing test for null transition**

First, read the existing test file to understand conventions:

Run: `uv run pytest tests/test_integrations.py --collect-only 2>&1 | head -30`

Then add this test to `tests/test_integrations.py`:

```python
def test_jira_update_task_status_returns_false_on_missing_transition(monkeypatch):
    from wizard.integrations import JiraClient

    client = JiraClient(base_url="https://jira.example.com", token="tok", project_key="ENG", email="a@b.com")
    # Stub _get_transition_id to return None
    monkeypatch.setattr(client, "_get_transition_id", lambda *args: None)
    result = client.update_task_status("ENG-1", "Nonexistent Status")
    assert result is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_integrations.py::test_jira_update_task_status_returns_false_on_missing_transition -v`
Expected: FAIL — currently the code sends `None` to the API, which raises an HTTPError (or the test client isn't set up). The point is the current code does not gracefully handle `None`.

- [ ] **Step 3: Add null guard to update_task_status**

In `src/wizard/integrations.py`, replace lines 98-109:

```python
    def update_task_status(self, source_id: str, status: str) -> bool:
        client = self._require_client()
        try:
            response = client.post(
                f"/issue/{source_id}/transitions",
                json={"transition": {"id": self._get_transition_id(source_id, status)}},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.warning("Jira update_task_status failed: %s", e)
            return False
```

with:

```python
    def update_task_status(self, source_id: str, status: str) -> bool:
        client = self._require_client()
        transition_id = self._get_transition_id(source_id, status)
        if transition_id is None:
            logger.warning(
                "No Jira transition found for status %r on %s", status, source_id
            )
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

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_integrations.py::test_jira_update_task_status_returns_false_on_missing_transition -v`
Expected: PASS.

- [ ] **Step 5: Run all integration tests**

Run: `uv run pytest tests/test_integrations.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/wizard/integrations.py tests/test_integrations.py
git commit -m "fix: guard against null Jira transition ID

_get_transition_id can return None when no matching transition exists.
Previously this sent null to the Jira API causing a 400. Now returns
False with a specific warning log."
```

---

### Task 6: Fix sqlite3 connection leak in doctor.py

**Files:**
- Modify: `src/wizard/cli/doctor.py:48-56`

- [ ] **Step 1: Wrap sqlite3 connection in try/finally**

In `src/wizard/cli/doctor.py`, replace lines 48-56:

```python
    try:
        conn = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
```

with:

```python
    try:
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

The outer `except Exception as exc:` on line 62 remains unchanged and still catches any error from `execute`. The `finally` ensures `conn.close()` runs whether `execute` succeeds or raises.

- [ ] **Step 2: Run existing doctor-related tests (if any)**

Run: `uv run pytest -v -k "doctor"`
Expected: PASS (or no tests collected — doctor checks are integration-heavy).

- [ ] **Step 3: Commit**

```bash
git add src/wizard/cli/doctor.py
git commit -m "fix: ensure sqlite3 connection closes on error in doctor check"
```

---

### Task 7: Fix closure capture in WriteBackService

**Files:**
- Modify: `src/wizard/services.py:231-251`

- [ ] **Step 1: Capture notion_id to local in push_task_due_date**

In `src/wizard/services.py`, replace lines 231-241:

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

with:

```python
    def push_task_due_date(self, task: Task) -> WriteBackStatus:
        """Push due_date to Notion if task has notion_id."""
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        if not task.due_date:
            return WriteBackStatus(ok=False, error="Task has no due_date")
        notion_id = task.notion_id
        due_date_iso = task.due_date.isoformat()
        return self._call(
            lambda: self._notion.update_task_due_date(notion_id, due_date_iso),
            "WriteBack push_task_due_date",
        )
```

- [ ] **Step 2: Capture notion_id to local in push_task_priority**

In `src/wizard/services.py`, replace lines 243-251:

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

with:

```python
    def push_task_priority(self, task: Task) -> WriteBackStatus:
        """Push priority to Notion if task has notion_id."""
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        notion_id = task.notion_id
        priority_label = PriorityMapper.local_to_notion(task.priority)
        return self._call(
            lambda: self._notion.update_task_priority(notion_id, priority_label),
            "WriteBack push_task_priority",
        )
```

- [ ] **Step 3: Run services tests**

Run: `uv run pytest tests/test_services.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/wizard/services.py
git commit -m "fix: capture notion_id before lambda in writeback methods

push_task_due_date and push_task_priority captured task.notion_id by
reference. Now matches the pattern used in push_task_status and
append_task_outcome."
```

---

### Task 8: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Verify phone scrubbing manually**

Run: `uv run python -c "from wizard.security import SecurityService; r = SecurityService().scrub('call +44 7700 900000 or +1 555 123 4567'); print(r.clean)"`
Expected: Output contains `[PHONE_1]` and `[PHONE_2]`, no raw phone numbers.

- [ ] **Step 3: Verify SecretStr masking**

Run: `uv run python -c "from wizard.config import Settings; s = Settings(); print(repr(s.jira.token)); print(repr(s.notion.token))"`
Expected: Output shows `SecretStr('**********')` (masked), not the raw token value.
