# JiraClient Structural Alignment with NotionClient

**Date:** 2026-04-10
**Scope:** `src/integrations.py` — `JiraClient` class only
**Blast radius:** JiraClient internals + JiraClient tests. No changes to services, tools, or config.

## Problem

`JiraClient` and `NotionClient` live in the same module but follow different structural patterns:

- NotionClient stores a pre-configured SDK client (`self._client`); JiraClient stores raw credentials and builds headers per-request.
- NotionClient uses `self._client is None` as the not-configured sentinel and raises `ConfigurationError`; JiraClient checks `self._token` with inconsistent behavior (raises in one method, silently returns `False` in another).
- NotionClient catches SDK errors, logs warnings, and returns safe fallbacks; JiraClient lets HTTP errors propagate from `fetch_open_tasks` and swallows them silently in `update_task_status`.

The public API and return shapes are fine. The inconsistency is internal.

## Decision

Align JiraClient's internals to match NotionClient's patterns. No new dependencies. No public API changes.

## Changes

### 1. Constructor — store a configured `httpx.Client`

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
```

Removes: `self._token`, `_headers()` method.

### 2. Configuration guard — consistent `ConfigurationError`

Both methods check `self._client is None` and raise `ConfigurationError("Jira token not configured")`. No silent `return False` on missing config.

### 3. Error handling — catch, log, return safe fallback

Catch `httpx.HTTPStatusError` (from `raise_for_status()`) and `httpx.ConnectError`/`httpx.TimeoutException` (network failures). Use the common parent `httpx.HTTPError` for simplicity — this matches the current `update_task_status` catch and covers all transport + status errors.

```python
# fetch_open_tasks
except httpx.HTTPError as e:
    logger.warning("Jira fetch_open_tasks failed: %s", e)
    return []

# update_task_status
except httpx.HTTPError as e:
    logger.warning("Jira update_task_status failed: %s", e)
    return False
```

### 4. Request paths — relative, base URL on client

```python
# Before
url = f"{self._base_url}/rest/api/2/search"
response = httpx.get(url, params=..., headers=self._headers(), timeout=_HTTPX_TIMEOUT)

# After
response = self._client.get("/search", params=...)
```

## What does NOT change

- Public API: `fetch_open_tasks() -> list[dict]`, `update_task_status(source_id, status) -> bool`
- Return dict shape from `fetch_open_tasks` (key, summary, status, priority, issue_type, url)
- NotionClient (no changes)
- Services layer (no changes)
- Tools layer (no changes)
- Config (no changes)

## Test impact

`test_integrations.py` tests for `JiraClient` will need updates:

- Constructor mocking changes (no more `_headers()` to patch; mock the `httpx.Client` instance or use `respx`)
- `update_task_status` with missing config now raises `ConfigurationError` instead of returning `False`

## Pattern reference

| Aspect | NotionClient | JiraClient (after) |
|---|---|---|
| Client storage | `self._client = NotionSdkClient(auth=token) if token else None` | `self._client = httpx.Client(...) if token else None` |
| Not-configured guard | `if self._client is None: raise ConfigurationError(...)` | Same |
| Error handling | `except APIResponseError as e: logger.warning(...)` | `except httpx.HTTPError as e: logger.warning(...)` |
| Safe fallbacks | `return []`, `return None`, `return False` | Same |
