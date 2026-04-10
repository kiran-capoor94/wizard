# JiraClient Structural Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align `JiraClient` internals with `NotionClient` patterns — stored client instance, consistent config guards, uniform error handling with logging.

**Architecture:** Replace raw credential storage + per-request header construction with a pre-configured `httpx.Client` instance. Standardise error handling to catch-log-return-fallback, matching `NotionClient`. No public API changes.

**Tech Stack:** Python, httpx, respx (test mocking), pytest

**Spec:** `docs/superpowers/specs/2026-04-10-jira-client-alignment-design.md`

---

### Task 1: Update tests for new JiraClient constructor and config guard

The existing tests patch `httpx.get` and `httpx.post` at module level. After the refactor, `JiraClient` will use a stored `httpx.Client` instance, so tests need to mock the instance methods instead. Use `respx` (already in dev deps) for cleaner HTTP mocking.

**Files:**
- Modify: `tests/test_integrations.py:1-71` (Jira test section only)

- [ ] **Step 1: Update the `make_jira_client` helper and config guard test**

Replace the existing Jira test block (lines 1-71) with:

```python
import pytest
import httpx
import respx
from unittest.mock import patch, MagicMock
from notion_client.errors import APIResponseError


def make_jira_client(base_url="https://jira.example.com", token="tok", project_key="ENG"):
    from src.integrations import JiraClient
    return JiraClient(base_url=base_url, token=token, project_key=project_key)


def test_jira_client_is_none_when_no_token():
    client = make_jira_client(token="")
    assert client._client is None


def test_jira_client_is_configured_when_token_provided():
    client = make_jira_client(token="tok")
    assert client._client is not None
    assert isinstance(client._client, httpx.Client)


def test_jira_raises_configuration_error_on_fetch_when_no_token():
    from src.integrations import ConfigurationError
    client = make_jira_client(token="")
    with pytest.raises(ConfigurationError):
        client.fetch_open_tasks()


def test_jira_raises_configuration_error_on_update_when_no_token():
    from src.integrations import ConfigurationError
    client = make_jira_client(token="")
    with pytest.raises(ConfigurationError):
        client.update_task_status("ENG-1", "done")
```

- [ ] **Step 2: Run the new config guard tests to verify they fail**

Run: `python -m pytest tests/test_integrations.py::test_jira_client_is_none_when_no_token tests/test_integrations.py::test_jira_client_is_configured_when_token_provided tests/test_integrations.py::test_jira_raises_configuration_error_on_fetch_when_no_token tests/test_integrations.py::test_jira_raises_configuration_error_on_update_when_no_token -v`

Expected: `test_jira_client_is_none_when_no_token` FAILS (no `_client` attribute), `test_jira_client_is_configured_when_token_provided` FAILS (no `_client` attribute), `test_jira_raises_configuration_error_on_update_when_no_token` FAILS (returns `False` instead of raising). `test_jira_raises_configuration_error_on_fetch_when_no_token` may pass since the old code already raises on empty token.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_integrations.py
git commit -m "test: add failing tests for JiraClient constructor and config guard alignment"
```

---

### Task 2: Refactor JiraClient constructor and config guards

**Files:**
- Modify: `src/integrations.py:18-70` (JiraClient class)

- [ ] **Step 1: Replace the JiraClient class**

Replace lines 18-70 in `src/integrations.py` (the entire `JiraClient` class) with:

```python
class JiraClient:
    def __init__(self, base_url: str, token: str, project_key: str):
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._client: httpx.Client | None = (
            httpx.Client(
                base_url=f"{self._base_url}/rest/api/2",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=_HTTPX_TIMEOUT,
            )
            if token
            else None
        )

    def fetch_open_tasks(self) -> list[dict]:
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        try:
            jql = f"project={self._project_key} AND statusCategory != Done ORDER BY priority DESC"
            response = self._client.get("/search", params={"jql": jql, "maxResults": 50})
            response.raise_for_status()
            issues = response.json().get("issues", [])
            return [
                {
                    "key": issue["key"],
                    "summary": issue["fields"]["summary"],
                    "status": issue["fields"]["status"]["name"],
                    "priority": issue["fields"]["priority"]["name"],
                    "issue_type": issue["fields"]["issuetype"]["name"],
                    "url": issue["fields"].get("self", ""),
                }
                for issue in issues
            ]
        except httpx.HTTPError as e:
            logger.warning("Jira fetch_open_tasks failed: %s", e)
            return []

    def update_task_status(self, source_id: str, status: str) -> bool:
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        try:
            response = self._client.post(
                f"/issue/{source_id}/transitions",
                json={"transition": {"name": status}},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.warning("Jira update_task_status failed: %s", e)
            return False
```

- [ ] **Step 2: Run the config guard tests to verify they pass**

Run: `python -m pytest tests/test_integrations.py::test_jira_client_is_none_when_no_token tests/test_integrations.py::test_jira_client_is_configured_when_token_provided tests/test_integrations.py::test_jira_raises_configuration_error_on_fetch_when_no_token tests/test_integrations.py::test_jira_raises_configuration_error_on_update_when_no_token -v`

Expected: All 4 PASS.

- [ ] **Step 3: Commit**

```bash
git add src/integrations.py
git commit -m "refactor: align JiraClient constructor and config guards with NotionClient"
```

---

### Task 3: Update tests for fetch_open_tasks with respx

Now that `JiraClient` uses a stored `httpx.Client`, the old `patch("httpx.get")` approach won't work. Use `respx` to mock HTTP transport on the client instance.

**Files:**
- Modify: `tests/test_integrations.py` (replace `test_jira_fetch_open_tasks_returns_list`)

- [ ] **Step 1: Add the respx-based fetch test and error test**

Add after the config guard tests, replacing the old `test_jira_fetch_open_tasks_returns_list`:

```python
@respx.mock
def test_jira_fetch_open_tasks_returns_list():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "ENG-1",
                        "fields": {
                            "summary": "Fix login",
                            "status": {"name": "In Progress"},
                            "priority": {"name": "High"},
                            "issuetype": {"name": "Bug"},
                            "self": "https://jira.example.com/rest/api/2/issue/ENG-1",
                        },
                    }
                ]
            },
        )
    )
    client = make_jira_client()
    tasks = client.fetch_open_tasks()

    assert len(tasks) == 1
    assert tasks[0]["key"] == "ENG-1"
    assert tasks[0]["summary"] == "Fix login"
    assert tasks[0]["status"] == "In Progress"
    assert tasks[0]["priority"] == "High"
    assert tasks[0]["issue_type"] == "Bug"


@respx.mock
def test_jira_fetch_open_tasks_returns_empty_on_http_error():
    respx.get("https://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(500)
    )
    client = make_jira_client()
    tasks = client.fetch_open_tasks()

    assert tasks == []
```

- [ ] **Step 2: Run the fetch tests**

Run: `python -m pytest tests/test_integrations.py::test_jira_fetch_open_tasks_returns_list tests/test_integrations.py::test_jira_fetch_open_tasks_returns_empty_on_http_error -v`

Expected: Both PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integrations.py
git commit -m "test: update fetch_open_tasks tests to use respx with stored httpx.Client"
```

---

### Task 4: Update tests for update_task_status with respx

**Files:**
- Modify: `tests/test_integrations.py` (replace `test_jira_update_task_status_*` tests)

- [ ] **Step 1: Add the respx-based update tests**

Replace the old `test_jira_update_task_status_returns_true_on_success` and `test_jira_update_task_status_returns_false_on_error` with:

```python
@respx.mock
def test_jira_update_task_status_returns_true_on_success():
    respx.post("https://jira.example.com/rest/api/2/issue/ENG-1/transitions").mock(
        return_value=httpx.Response(204)
    )
    client = make_jira_client()
    result = client.update_task_status("ENG-1", "done")

    assert result is True


@respx.mock
def test_jira_update_task_status_returns_false_on_http_error():
    respx.post("https://jira.example.com/rest/api/2/issue/ENG-1/transitions").mock(
        return_value=httpx.Response(500)
    )
    client = make_jira_client()
    result = client.update_task_status("ENG-1", "done")

    assert result is False
```

- [ ] **Step 2: Run the update tests**

Run: `python -m pytest tests/test_integrations.py::test_jira_update_task_status_returns_true_on_success tests/test_integrations.py::test_jira_update_task_status_returns_false_on_http_error -v`

Expected: Both PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integrations.py
git commit -m "test: update update_task_status tests to use respx"
```

---

### Task 5: Run full test suite and verify no regressions

**Files:**
- None (verification only)

- [ ] **Step 1: Run the full integration test file**

Run: `python -m pytest tests/test_integrations.py -v`

Expected: All tests PASS. Jira tests use respx, Notion tests unchanged. No old Jira tests remain (the `patch("httpx.get")` / `patch("httpx.post")` tests are fully replaced).

- [ ] **Step 2: Run the full test suite to check for regressions**

Run: `python -m pytest -v`

Expected: All tests PASS. The public API of `JiraClient` hasn't changed, so `test_services.py` and `test_tools.py` should be unaffected.

- [ ] **Step 3: Commit any cleanup if needed, otherwise skip**

Only commit if there were fixups. Otherwise, move on.
