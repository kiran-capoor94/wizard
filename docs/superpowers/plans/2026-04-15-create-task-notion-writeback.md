# create_task Notion Writeback Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `create_task` always failing Notion writeback by removing hardcoded property names and surfacing real API errors; add a live doctor check that validates the Notion DB schema upfront.

**Architecture:** Two-layer fix — `NotionClient.create_task_page` and `create_meeting_page` are updated to use `self._schema` for property names and to stop swallowing `APIResponseError`. `_check_notion_schema` in the CLI is replaced with a live validation that calls `fetch_db_properties` and checks each schema field exists with the correct type.

**Tech Stack:** Python, `notion-client>=3.0`, `wizard.notion_discovery.fetch_db_properties`, Typer CLI, pytest

---

## File Map

| File | Change |
|---|---|
| `src/wizard/integrations.py` | Fix `create_task_page` and `create_meeting_page`: use `self._schema`, remove `except APIResponseError` |
| `src/wizard/cli/main.py` | Replace `_check_notion_schema` body; add `_validate_properties` helper |
| `tests/test_integrations.py` | Add schema field tests + error propagation tests; update two existing tests |
| `tests/test_cli.py` | Add three doctor check unit tests; update `test_doctor_all_checks_pass_with_valid_setup` |

---

### Task 1: Fix `create_task_page` — schema fields and error propagation

**Files:**
- Modify: `src/wizard/integrations.py:331-362`
- Test: `tests/test_integrations.py`

- [ ] **Step 1: Write failing test — schema field names**

Add to `tests/test_integrations.py` after the existing `create_task_page` tests (after line 443):

```python
def test_notion_create_task_page_uses_schema_property_names():
    """create_task_page must use schema field names, not hardcoded strings."""
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings(
        task_name="Name",
        task_status="State",
        task_priority="Prio",
        task_jira_key="Jira Link",
        task_due_date="Deadline",
    )
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.return_value = {"id": "page-id"}

        client = make_notion_client(schema=schema)
        client.create_task_page(
            name="My task",
            status="Not started",
            priority="High",
            jira_url="https://org.atlassian.net/browse/ENG-1",
            due_date="2026-04-20",
        )

    props = mock_client_instance.pages.create.call_args.kwargs["properties"]
    assert "Name" in props
    assert "State" in props
    assert "Prio" in props
    assert "Jira Link" in props
    assert "Deadline" in props
    assert "Task" not in props
    assert "Status" not in props


def test_notion_create_task_page_propagates_api_error():
    """create_task_page must propagate APIResponseError, not return None."""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.side_effect = error

        client = make_notion_client()
        with pytest.raises(APIResponseError):
            client.create_task_page(name="Task", status="Backlog")
```

- [ ] **Step 2: Run to confirm both new tests fail**

```bash
cd /home/agntx/Documents/repos/personal/wizard
uv run pytest tests/test_integrations.py::test_notion_create_task_page_uses_schema_property_names tests/test_integrations.py::test_notion_create_task_page_propagates_api_error -v
```

Expected: both FAIL (`AssertionError: assert 'Task' not in props` and `Failed: DID NOT RAISE`)

- [ ] **Step 3: Extend `make_notion_client` to accept `schema`**

In `tests/test_integrations.py`, update the `make_notion_client` helper (currently at line ~198):

```python
def make_notion_client(
    token="tok",
    sisu_work_page_id="parent-abc",
    tasks_db_id="db-tasks",
    meetings_db_id="db-meetings",
    schema=None,
):
    from wizard.integrations import NotionClient
    return NotionClient(
        token=token,
        sisu_work_page_id=sisu_work_page_id,
        tasks_db_id=tasks_db_id,
        meetings_db_id=meetings_db_id,
        schema=schema,
    )
```

- [ ] **Step 4: Implement the fix in `create_task_page`**

In `src/wizard/integrations.py`, replace the `create_task_page` method body (lines 331–362) with:

```python
def create_task_page(
    self,
    name: str,
    status: str,
    priority: str | None = None,
    jira_url: str | None = None,
    due_date: str | None = None,
) -> str | None:
    """Create page in Tasks DB, return page_id."""
    client = self._require_client()

    properties: dict = {
        self._schema.task_name: {"title": [{"text": {"content": name}}]},
        self._schema.task_status: {"status": {"name": status}},
    }

    if priority:
        properties[self._schema.task_priority] = {"select": {"name": priority}}
    if jira_url:
        properties[self._schema.task_jira_key] = {"url": jira_url}
    if due_date:
        properties[self._schema.task_due_date] = {"date": {"start": due_date}}

    response = client.pages.create(
        parent={"database_id": self._tasks_db_id},
        properties=properties,
    )
    return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]
```

Also update the existing test that expects the old `None`-on-error behaviour. In `tests/test_integrations.py`, rename and update `test_notion_create_task_page_returns_none_on_api_error`:

```python
def test_notion_create_task_page_propagates_api_error_from_pages_create():
    """create_task_page propagates APIResponseError from pages.create."""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.side_effect = error

        client = make_notion_client()
        with pytest.raises(APIResponseError):
            client.create_task_page(name="Task", status="Backlog")
```

(This replaces the test `test_notion_create_task_page_returns_none_on_api_error` entirely — same name location, different content and new name.)

- [ ] **Step 5: Run all `create_task_page` tests to confirm pass**

```bash
uv run pytest tests/test_integrations.py -k "create_task_page" -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_integrations.py src/wizard/integrations.py
git commit -m "fix: create_task_page uses schema property names, propagates APIResponseError"
```

---

### Task 2: Fix `create_meeting_page` — schema fields and error propagation

**Files:**
- Modify: `src/wizard/integrations.py:364-392`
- Test: `tests/test_integrations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_integrations.py` after the existing `create_meeting_page` tests (after line 514):

```python
def test_notion_create_meeting_page_uses_schema_property_names():
    """create_meeting_page must use schema field names, not hardcoded strings."""
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings(
        meeting_title="Title",
        meeting_url="Recording",
        meeting_summary="Notes",
    )
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.return_value = {"id": "page-id"}

        client = make_notion_client(schema=schema)
        client.create_meeting_page(
            title="Sprint Review",
            category="Planning",
            krisp_url="https://krisp.ai/m/abc",
            summary="Reviewed sprint velocity",
        )

    props = mock_client_instance.pages.create.call_args.kwargs["properties"]
    assert "Title" in props
    assert "Recording" in props
    assert "Notes" in props
    assert "Meeting name" not in props
    assert "Krisp URL" not in props
    assert "Summary" not in props
    # "Category" stays hardcoded
    assert "Category" in props


def test_notion_create_meeting_page_propagates_api_error():
    """create_meeting_page must propagate APIResponseError, not return None."""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.side_effect = error

        client = make_notion_client()
        with pytest.raises(APIResponseError):
            client.create_meeting_page(title="Meeting", category="Planning")
```

- [ ] **Step 2: Run to confirm both new tests fail**

```bash
uv run pytest tests/test_integrations.py::test_notion_create_meeting_page_uses_schema_property_names tests/test_integrations.py::test_notion_create_meeting_page_propagates_api_error -v
```

Expected: both FAIL

- [ ] **Step 3: Implement the fix in `create_meeting_page`**

In `src/wizard/integrations.py`, replace the `create_meeting_page` method body (lines 364–392) with:

```python
def create_meeting_page(
    self,
    title: str,
    category: str,
    krisp_url: str | None = None,
    summary: str | None = None,
) -> str | None:
    """Create page in Meeting Notes DB, return page_id."""
    client = self._require_client()

    properties = {
        self._schema.meeting_title: {"title": [{"text": {"content": title}}]},
        "Category": {"multi_select": [{"name": category}]},
    }

    if krisp_url:
        properties[self._schema.meeting_url] = {"url": krisp_url}
    if summary:
        properties[self._schema.meeting_summary] = {"rich_text": [{"text": {"content": summary}}]}

    response = client.pages.create(
        parent={"database_id": self._meetings_db_id},
        properties=properties,
    )
    return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]
```

Also update the existing `test_notion_create_meeting_page_returns_none_on_api_error` test (lines ~495–506) to reflect the new behaviour:

```python
def test_notion_create_meeting_page_propagates_api_error_from_pages_create():
    """create_meeting_page propagates APIResponseError from pages.create."""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.side_effect = error

        client = make_notion_client()
        with pytest.raises(APIResponseError):
            client.create_meeting_page(title="Meeting", category="Planning")
```

- [ ] **Step 4: Run all `create_meeting_page` tests to confirm pass**

```bash
uv run pytest tests/test_integrations.py -k "create_meeting_page" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_integrations.py src/wizard/integrations.py
git commit -m "fix: create_meeting_page uses schema property names, propagates APIResponseError"
```

---

### Task 3: Enhance `_check_notion_schema` with live DB validation

**Files:**
- Modify: `src/wizard/cli/main.py:280-286`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write three failing unit tests for `_check_notion_schema`**

Add to `tests/test_cli.py` (before or after the existing doctor tests section):

```python
# --- _check_notion_schema unit tests ---


def test_check_notion_schema_passes_when_live_db_matches(tmp_path, monkeypatch):
    """_check_notion_schema returns True when all expected properties exist with correct types."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_db_id": "tasks-db",
            "meetings_db_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        "Task": "title",
        "Status": "status",
        "Priority": "select",
        "Due date": "date",
        "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.main import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is True
    assert "matches" in msg


def test_check_notion_schema_fails_when_task_property_missing(tmp_path, monkeypatch):
    """_check_notion_schema returns False when a tasks DB property is absent."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_db_id": "tasks-db",
            "meetings_db_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        # "Task" title property is missing
        "Status": "status",
        "Priority": "select",
        "Due date": "date",
        "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.main import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is False
    assert "Tasks DB" in msg
    assert "'Task'" in msg


def test_check_notion_schema_fails_when_property_has_wrong_type(tmp_path, monkeypatch):
    """_check_notion_schema returns False when a property exists but has the wrong type."""
    import json
    config = {
        "notion": {
            "token": "tok",
            "tasks_db_id": "tasks-db",
            "meetings_db_id": "meetings-db",
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))

    tasks_props = {
        "Task": "title",
        "Status": "status",
        "Priority": "multi_select",  # wrong — should be "select"
        "Due date": "date",
        "Jira": "url",
    }
    meetings_props = {
        "Meeting name": "title",
        "Date": "date",
        "Krisp URL": "url",
        "Summary": "rich_text",
        "Category": "multi_select",
    }
    with patch("wizard.notion_discovery.fetch_db_properties", side_effect=[tasks_props, meetings_props]), \
         patch("wizard.integrations.NotionSdkClient"):
        from wizard.cli.main import _check_notion_schema
        ok, msg = _check_notion_schema()

    assert ok is False
    assert "Tasks DB" in msg
    assert "multi_select" in msg
    assert "select" in msg
```

- [ ] **Step 2: Run to confirm all three fail**

```bash
uv run pytest tests/test_cli.py::test_check_notion_schema_passes_when_live_db_matches tests/test_cli.py::test_check_notion_schema_fails_when_task_property_missing tests/test_cli.py::test_check_notion_schema_fails_when_property_has_wrong_type -v
```

Expected: all FAIL (old implementation just checks config strings, doesn't call `fetch_db_properties`)

- [ ] **Step 3: Implement `_validate_properties` helper and new `_check_notion_schema`**

In `src/wizard/cli/main.py`, add `_validate_properties` as a module-level helper (place it just before `_check_notion_schema`):

```python
def _validate_properties(
    available: dict[str, str], expected: list[tuple[str, str]]
) -> list[str]:
    """Return error strings for each property that is missing or has the wrong type."""
    errors = []
    for name, expected_type in expected:
        if name not in available:
            errors.append(f"'{name}' not found (expected {expected_type})")
        elif available[name] != expected_type:
            errors.append(f"'{name}' is {available[name]}, expected {expected_type}")
    return errors
```

Replace the body of `_check_notion_schema` (lines 280–286) with:

```python
def _check_notion_schema() -> tuple[bool, str]:
    from wizard.config import Settings
    from wizard.integrations import NotionSdkClient
    from wizard import notion_discovery

    s = Settings()
    notion = s.notion
    schema = notion.notion_schema

    if not notion.tasks_db_id or not notion.meetings_db_id:
        return False, "Notion DB IDs not configured — run 'wizard setup --reconfigure-notion'"

    client = NotionSdkClient(auth=notion.token)
    tasks_props = notion_discovery.fetch_db_properties(client, notion.tasks_db_id)
    meetings_props = notion_discovery.fetch_db_properties(client, notion.meetings_db_id)

    task_fields: list[tuple[str, str]] = [
        (schema.task_name, "title"),
        (schema.task_status, "status"),
        (schema.task_priority, "select"),
        (schema.task_due_date, "date"),
        (schema.task_jira_key, "url"),
    ]
    meeting_fields: list[tuple[str, str]] = [
        (schema.meeting_title, "title"),
        (schema.meeting_date, "date"),
        (schema.meeting_url, "url"),
        (schema.meeting_summary, "rich_text"),
        ("Category", "multi_select"),
    ]

    task_errors = _validate_properties(tasks_props, task_fields)
    meeting_errors = _validate_properties(meetings_props, meeting_fields)

    parts = []
    if task_errors:
        parts.append(f"Tasks DB: {'; '.join(task_errors)}")
    if meeting_errors:
        parts.append(f"Meetings DB: {'; '.join(meeting_errors)}")

    if parts:
        return False, " | ".join(parts)
    return True, "Notion schema matches live DB"
```

- [ ] **Step 4: Update `test_doctor_all_checks_pass_with_valid_setup` to mock the new check**

In `tests/test_cli.py`, find `test_doctor_all_checks_pass_with_valid_setup` (line ~512) and add `_check_notion_schema` to the patched list:

```python
def test_doctor_all_checks_pass_with_valid_setup(tmp_path, monkeypatch):
    import json
    from unittest.mock import patch
    db_path = tmp_path / "wizard.db"
    db_path.touch()
    config = {
        "notion": {"token": "tok", "tasks_db_id": "t", "meetings_db_id": "m"},
        "jira": {"token": "jtok", "base_url": "https://jira.example.com", "project_key": "ENG"},
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(db_path))
    with patch("wizard.cli.main._check_db_tables", return_value=(True, "ok")), \
         patch("wizard.cli.main._check_migration_current", return_value=(True, "ok")), \
         patch("wizard.cli.main._check_agent_registrations", return_value=(True, "ok")), \
         patch("wizard.cli.main._check_allowlist_file", return_value=(True, "ok")), \
         patch("wizard.cli.main._check_skills_installed", return_value=(True, "ok")), \
         patch("wizard.cli.main._check_notion_schema", return_value=(True, "Notion schema matches live DB")):
        from typer.testing import CliRunner
        from wizard.cli.main import app
        runner_local = CliRunner()
        result = runner_local.invoke(app, ["doctor", "--all"])
    assert result.exit_code == 0
```

- [ ] **Step 5: Run all three new unit tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_check_notion_schema_passes_when_live_db_matches tests/test_cli.py::test_check_notion_schema_fails_when_task_property_missing tests/test_cli.py::test_check_notion_schema_fails_when_property_has_wrong_type -v
```

Expected: all PASS

- [ ] **Step 6: Run the full test suite to catch regressions**

```bash
uv run pytest tests/test_integrations.py tests/test_cli.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: _check_notion_schema validates live Notion DB property names and types"
```
