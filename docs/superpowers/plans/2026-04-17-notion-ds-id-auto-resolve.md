# Notion Data Source ID Auto-Resolve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw data source ID prompts in `_configure_notion` with Notion URL prompts that auto-resolve to data source IDs via the API.

**Architecture:** Two new pure helper functions (`_resolve_notion_page_id`, `_resolve_ds_id`) handle URL parsing and API lookup. `_configure_notion` constructs a `NotionSdkClient` after collecting the token, then uses a retry loop for each database URL prompt. All changes are in `main.py`; affected tests are updated in `test_cli.py`.

**Tech Stack:** Python, Typer, notion-client v3, re (stdlib), uv pytest

---

## File Map

| File | Change |
|------|--------|
| `src/wizard/cli/main.py` | Add `import re`; add `_resolve_notion_page_id`, `_resolve_ds_id` helpers; rewrite the two data-source-ID prompts in `_configure_notion` |
| `tests/test_cli.py` | Add `import pytest`; add tests for the two new helpers; update 6 existing Notion-flow tests to use URL input and mock `_resolve_ds_id` |

---

### Task 1: Add `_resolve_notion_page_id` and `_resolve_ds_id` helpers

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add `import pytest` to `tests/test_cli.py`**

The file currently starts with:
```python
import json
import sys
from pathlib import Path
from unittest.mock import patch
```

Add `import pytest` so that it becomes:
```python
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
```

- [ ] **Step 2: Write failing tests for `_resolve_notion_page_id`**

Add to `tests/test_cli.py`:

```python
def test_resolve_notion_page_id_extracts_from_workspace_url():
    from wizard.cli.main import _resolve_notion_page_id
    url = "https://www.notion.so/workspace/My-Tasks-abc123def456789012345678901234ab"
    assert _resolve_notion_page_id(url) == "abc123de-f456-7890-1234-5678901234ab"


def test_resolve_notion_page_id_extracts_from_short_url():
    from wizard.cli.main import _resolve_notion_page_id
    url = "https://www.notion.so/abc123def456789012345678901234ab"
    assert _resolve_notion_page_id(url) == "abc123de-f456-7890-1234-5678901234ab"


def test_resolve_notion_page_id_strips_query_params():
    from wizard.cli.main import _resolve_notion_page_id
    url = "https://www.notion.so/My-Tasks-abc123def456789012345678901234ab?v=xyz&p=foo"
    assert _resolve_notion_page_id(url) == "abc123de-f456-7890-1234-5678901234ab"


def test_resolve_notion_page_id_raises_on_invalid_url():
    from wizard.cli.main import _resolve_notion_page_id
    with pytest.raises(ValueError, match="Could not extract"):
        _resolve_notion_page_id("https://notion.so/workspace/no-id-here")
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /Users/kirancapoor/Documents/repos/wizard
uv run pytest tests/test_cli.py::test_resolve_notion_page_id_extracts_from_workspace_url tests/test_cli.py::test_resolve_notion_page_id_extracts_from_short_url tests/test_cli.py::test_resolve_notion_page_id_strips_query_params tests/test_cli.py::test_resolve_notion_page_id_raises_on_invalid_url -v
```

Expected: FAIL with `ImportError` or `AttributeError` (function doesn't exist yet)

- [ ] **Step 4: Add `import re` and `_resolve_notion_page_id` to `main.py`**

In `src/wizard/cli/main.py`, add `import re` to the stdlib imports block (after `import sys`):

```python
import re
```

Add this function before `_notion_is_configured` (around line 167):

```python
def _resolve_notion_page_id(url: str) -> str:
    """Extract 32-char hex page ID from a Notion URL and format as UUID.

    Handles:
      https://www.notion.so/workspace/My-Tasks-abc123def456789012345678901234ab
      https://www.notion.so/abc123def456789012345678901234ab
      https://www.notion.so/My-Tasks-abc123def456789012345678901234ab?v=...
    """
    path = url.split("?")[0]
    matches = re.findall(r"[0-9a-f]{32}", path.lower())
    if not matches:
        raise ValueError(f"Could not extract page ID from URL: {url}")
    raw = matches[-1]
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
```

- [ ] **Step 5: Run `_resolve_notion_page_id` tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_resolve_notion_page_id_extracts_from_workspace_url tests/test_cli.py::test_resolve_notion_page_id_extracts_from_short_url tests/test_cli.py::test_resolve_notion_page_id_strips_query_params tests/test_cli.py::test_resolve_notion_page_id_raises_on_invalid_url -v
```

Expected: PASS

- [ ] **Step 6: Write failing tests for `_resolve_ds_id`**

Add to `tests/test_cli.py`:

```python
def test_resolve_ds_id_returns_first_source_id():
    from unittest.mock import MagicMock
    from wizard.cli.main import _resolve_ds_id
    client = MagicMock()
    client.databases.retrieve.return_value = {
        "data_sources": [{"id": "ds-abc123"}, {"id": "ds-def456"}]
    }
    result = _resolve_ds_id(client, "abc123de-f456-7890-1234-5678901234ab")
    assert result == "ds-abc123"
    client.databases.retrieve.assert_called_once_with(
        database_id="abc123de-f456-7890-1234-5678901234ab"
    )


def test_resolve_ds_id_raises_when_no_sources():
    from unittest.mock import MagicMock
    from wizard.cli.main import _resolve_ds_id
    client = MagicMock()
    client.databases.retrieve.return_value = {"data_sources": []}
    with pytest.raises(ValueError, match="No data sources"):
        _resolve_ds_id(client, "abc123de-f456-7890-1234-5678901234ab")


def test_resolve_ds_id_raises_when_key_missing():
    from unittest.mock import MagicMock
    from wizard.cli.main import _resolve_ds_id
    client = MagicMock()
    client.databases.retrieve.return_value = {}
    with pytest.raises(ValueError, match="No data sources"):
        _resolve_ds_id(client, "abc123de-f456-7890-1234-5678901234ab")
```

- [ ] **Step 7: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::test_resolve_ds_id_returns_first_source_id tests/test_cli.py::test_resolve_ds_id_raises_when_no_sources tests/test_cli.py::test_resolve_ds_id_raises_when_key_missing -v
```

Expected: FAIL

- [ ] **Step 8: Add `_resolve_ds_id` to `main.py`**

Add immediately after `_resolve_notion_page_id`:

```python
def _resolve_ds_id(client, page_id: str) -> str:
    """Return the data source ID for the given Notion database page ID.

    Uses databases.retrieve() specifically to access the data_sources field —
    not for schema access (which would violate the CLAUDE.md rule).
    """
    response = client.databases.retrieve(database_id=page_id)
    sources = response.get("data_sources", [])
    if not sources:
        raise ValueError("No data sources found for this database")
    return sources[0]["id"]
```

- [ ] **Step 9: Run `_resolve_ds_id` tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_resolve_ds_id_returns_first_source_id tests/test_cli.py::test_resolve_ds_id_raises_when_no_sources tests/test_cli.py::test_resolve_ds_id_raises_when_key_missing -v
```

Expected: PASS

- [ ] **Step 10: Run full suite to confirm nothing broke**

```bash
uv run pytest tests/test_cli.py -q 2>&1 | tail -5
```

Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: add _resolve_notion_page_id and _resolve_ds_id helpers"
```

---

### Task 2: Update `_configure_notion` to use URL prompts + update affected tests

**Files:**
- Modify: `src/wizard/cli/main.py` (lines ~195-215, inside `_configure_notion`)
- Modify: `tests/test_cli.py` (6 existing tests)

- [ ] **Step 1: Rewrite `_configure_notion` in `main.py`**

Replace the current `_configure_notion` function body entirely. The current function is at lines ~177-199. Replace it with:

```python
def _configure_notion(cfg: dict, config_path: Path) -> None:
    """Prompt for all Notion credentials, save to config, run schema discovery."""
    typer.echo("\nNotion integration")
    token = typer.prompt("  Notion integration token (notion.so/profile/integrations)")
    cfg.setdefault("notion", {})["token"] = token
    typer.echo("  token: set")

    page_id = typer.prompt("  Daily page parent ID (Enter to skip)", default="")
    cfg["notion"]["daily_page_parent_id"] = page_id
    typer.echo(f"  daily page ID: {'set' if page_id else 'skipped'}")

    client = NotionSdkClient(auth=token)

    while True:
        tasks_url = typer.prompt("  Tasks database URL")
        try:
            pid = _resolve_notion_page_id(tasks_url)
            typer.echo("  → Resolving...", nl=False)
            tasks_ds_id = _resolve_ds_id(client, pid)
            typer.echo("  ok")
            cfg["notion"]["tasks_ds_id"] = tasks_ds_id
            typer.echo("  tasks database: set")
            break
        except Exception as exc:
            typer.echo(f"  failed: {exc}. Paste the database URL from Notion.")

    while True:
        meetings_url = typer.prompt("  Meetings database URL")
        try:
            pid = _resolve_notion_page_id(meetings_url)
            typer.echo("  → Resolving...", nl=False)
            meetings_ds_id = _resolve_ds_id(client, pid)
            typer.echo("  ok")
            cfg["notion"]["meetings_ds_id"] = meetings_ds_id
            typer.echo("  meetings database: set")
            break
        except Exception as exc:
            typer.echo(f"  failed: {exc}. Paste the database URL from Notion.")

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    _run_notion_discovery(config_path)
```

- [ ] **Step 2: Update the 6 affected tests in `tests/test_cli.py`**

These tests currently pass bare IDs (`my-tasks-id`) as input. They must now pass valid Notion URLs and mock both `NotionSdkClient` and `_resolve_ds_id`.

Use these two test URLs consistently across all updated tests:
- Tasks: `https://notion.so/workspace/Tasks-abc123def456789012345678901234ab`
- Meetings: `https://notion.so/workspace/Meetings-def456789012345678901234abcdef01`

**Replace `test_setup_notion_collects_token_and_ids`:**

```python
def test_setup_notion_collects_token_and_ids(tmp_path):
    """Selecting Notion (1) prompts for token, daily page ID, tasks URL, meetings URL; resolves ds IDs."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\nmy-page-id\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["token"] == "my-token"
    assert cfg["notion"]["daily_page_parent_id"] == "my-page-id"
    assert cfg["notion"]["tasks_ds_id"] == "tasks-ds-id"
    assert cfg["notion"]["meetings_ds_id"] == "meetings-ds-id"
```

**Replace `test_setup_notion_runs_discovery`:**

```python
def test_setup_notion_runs_discovery(tmp_path):
    """After collecting Notion credentials, setup calls _run_notion_discovery."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery") as mock_disc, \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    mock_disc.assert_called_once()
```

**Replace `test_setup_notion_optional_daily_page_id_can_be_skipped`:**

```python
def test_setup_notion_optional_daily_page_id_can_be_skipped(tmp_path):
    """Pressing Enter on daily page ID prompt skips it (leaves field empty)."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["daily_page_parent_id"] == ""
```

**Replace `test_setup_both_configures_notion_and_jira`:**

```python
def test_setup_both_configures_notion_and_jira(tmp_path):
    """Selecting Both (3) runs both _configure_notion and _configure_jira."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="3\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["token"] == "my-token"
    assert cfg["jira"]["token"] == "jira-token"
```

**Replace `test_setup_both_does_not_clobber_notion_schema`:**

```python
def test_setup_both_does_not_clobber_notion_schema(tmp_path):
    """When Both is selected, Jira write must not discard notion_schema written by discovery."""
    wizard_dir = tmp_path / ".wizard"

    def fake_discovery(config_path):
        with open(config_path) as f:
            cfg = json.load(f)
        cfg.setdefault("notion", {})["notion_schema"] = {"task_name": "Task"}
        with open(config_path, "w") as f:
            json.dump(cfg, f, indent=2)

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery", side_effect=fake_discovery), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="3\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
            )

    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg.get("notion", {}).get("notion_schema") == {"task_name": "Task"}
    assert cfg["jira"]["token"] == "jira-token"
```

**Replace `test_setup_final_summary_shows_configured_integrations`:**

Find this test (it provides `input="1\nmy-token\n\ntasks-id\nmeetings-id\n"`) and update it:

```python
def test_setup_final_summary_shows_configured_integrations(tmp_path):
    """Final summary lists Notion as configured and Jira as skipped."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    assert result.exit_code == 0
    assert "notion" in result.output.lower()
    assert "configured" in result.output.lower()
    assert "jira" in result.output.lower()
    assert "wizard configure --jira" in result.output
```

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest tests/test_cli.py -q 2>&1 | tail -5
```

Expected: All PASS

- [ ] **Step 4: Add a test for the URL resolution retry loop**

Add to `tests/test_cli.py`:

```python
def test_setup_notion_retries_on_invalid_url(tmp_path):
    """If the first URL fails resolution, setup re-prompts until a valid URL is given."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=[
                 ValueError("No data sources found"),  # first tasks attempt fails
                 "tasks-ds-id",                         # second tasks attempt succeeds
                 "meetings-ds-id",
             ]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input=(
                    "1\nmy-token\n\n"
                    "https://notion.so/workspace/Bad-abc123def456789012345678901234ab\n"   # fails
                    "https://notion.so/workspace/Tasks-abc123def456789012345678901234ab\n" # succeeds
                    "https://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n"
                ),
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["tasks_ds_id"] == "tasks-ds-id"
    assert "failed" in result.output.lower()
```

- [ ] **Step 5: Run the new retry test**

```bash
uv run pytest tests/test_cli.py::test_setup_notion_retries_on_invalid_url -v
```

Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/test_cli.py -q 2>&1 | tail -5
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: accept Notion database URLs in setup and auto-resolve to data source IDs"
```

---

## Self-Review

**Spec coverage:**
- ✅ Accept full Notion URL — Task 2 (`_configure_notion` URL prompts)
- ✅ Extract page ID from URL — Task 1 (`_resolve_notion_page_id`)
- ✅ Call API to get data source ID — Task 1 (`_resolve_ds_id`)
- ✅ User never sees/handles a data source ID — Task 2
- ✅ Retry on failure without exiting setup — Task 2 (while loop)
- ✅ Three URL formats handled — Task 1 (`?` split + regex on path)
- ✅ Error handling per spec table — Task 2 (except block prints and re-prompts)

**No placeholders found.**

**Type consistency:** `_resolve_ds_id(client, page_id: str) -> str` — `client` is untyped to avoid importing the SDK type; consistent across Tasks 1 and 2. `_resolve_notion_page_id(url: str) -> str` — consistent.

**Note on `test_setup_notion_configuration_error_exits_cleanly`:** This test (added in the previous feature) patches `_run_notion_discovery` with a `ConfigurationError`. Its input is `"1\nmy-token\n\ntasks-id\nmeetings-id\n"` which will no longer match the new URL prompts — it will hang waiting for valid URLs. This test must also be updated in Task 2 (add `NotionSdkClient` and `_resolve_ds_id` mocks, change input to use URLs). Add to Step 2:

**Replace `test_setup_notion_configuration_error_exits_cleanly`:**

```python
def test_setup_notion_configuration_error_exits_cleanly(tmp_path):
    """If Notion schema discovery raises ConfigurationError, setup exits with code 1 and a clean message."""
    from wizard.integrations import ConfigurationError
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery", side_effect=ConfigurationError("task_name required")), \
             patch("wizard.cli.main.NotionSdkClient"), \
             patch("wizard.cli.main._resolve_ds_id", side_effect=["tasks-ds-id", "meetings-ds-id"]):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nhttps://notion.so/workspace/Tasks-abc123def456789012345678901234ab\nhttps://notion.so/workspace/Meetings-def456789012345678901234abcdef01\n",
            )
    assert result.exit_code != 0
    assert "notion configuration failed" in result.output.lower() or "notion configuration failed" in (result.stderr or "").lower()
```

This update belongs in Step 2 of Task 2 alongside the other test replacements.
