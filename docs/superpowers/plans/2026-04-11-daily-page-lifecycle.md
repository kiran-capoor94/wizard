# Daily Page Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate daily page creation, discovery, and archival in Notion so `session_start` always resolves today's page and `session_end` writes to it without stale config.

**Architecture:** `NotionClient` gains methods to list children of the SISU Work page, find/create today's daily page by title, and archive stale pages. `session_start` calls `ensure_daily_page()` and stores the resolved page ID on `WizardSession`. `session_end` reads it back for write-back. Static `daily_page_id` config is replaced by `sisu_work_page_id`.

**Tech Stack:** Python 3.14, SQLModel, Alembic, notion-client SDK, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/config.py` | Modify | Remove `daily_page_id`, add `sisu_work_page_id` |
| `src/models.py` | Modify | Add `daily_page_id` column to `WizardSession` |
| `src/schemas.py` | Modify | Add `DailyPageResult`, update `SessionStartResponse` |
| `src/integrations.py` | Modify | New methods on `NotionClient`, update constructor and `update_daily_page` |
| `src/services.py` | Modify | Update `push_session_summary` to use `session.daily_page_id` |
| `src/tools.py` | Modify | `session_start` calls `ensure_daily_page`, `session_end` uses session page ID |
| `src/deps.py` | Modify | Update `NotionClient` construction |
| `config.json` | Modify | Replace `daily_page_id` with `sisu_work_page_id` |
| `alembic/versions/` | Create | Migration for `daily_page_id` column |
| `tests/test_config.py` | Modify | Update config tests |
| `tests/test_integrations.py` | Modify | Add tests for new NotionClient methods |
| `tests/test_services.py` | Modify | Update push_session_summary tests |
| `tests/test_tools.py` | Modify | Update session_start/session_end tests |

---

### Task 1: Config, Model, Schema, and Migration

**Files:**
- Modify: `src/config.py:43-47`
- Modify: `src/models.py:107-114`
- Modify: `src/schemas.py:178-183,220-222`
- Create: `alembic/versions/<hash>_add_daily_page_id_to_wizardsession.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test for new config field**

In `tests/test_config.py`, add:

```python
def test_notion_has_sisu_work_page_id():
    from src.config import NotionSettings

    s = NotionSettings()
    assert hasattr(s, "sisu_work_page_id")
    assert s.sisu_work_page_id == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_config.py::test_notion_has_sisu_work_page_id -v`

Expected: FAIL with `AssertionError`

- [ ] **Step 3: Update config — remove daily_page_id, add sisu_work_page_id**

In `src/config.py`, replace:

```python
class NotionSettings(BaseModel):
    daily_page_id: str = ""
    tasks_db_id: str = ""
    meetings_db_id: str = ""
    token: str = ""
```

With:

```python
class NotionSettings(BaseModel):
    sisu_work_page_id: str = ""
    tasks_db_id: str = ""
    meetings_db_id: str = ""
    token: str = ""
```

- [ ] **Step 4: Run config test to verify it passes**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_config.py::test_notion_has_sisu_work_page_id -v`

Expected: PASS

- [ ] **Step 5: Add daily_page_id column to WizardSession model**

In `src/models.py`, change the `WizardSession` class:

```python
class WizardSession(TimestampMixin, table=True):
    __tablename__ = "wizardsession"  # pyright: ignore[reportAssignmentType, reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    summary: str | None = None
    daily_page_id: str | None = None
    notes: list["Note"] = Relationship(back_populates="session")
```

- [ ] **Step 6: Add DailyPageResult schema and update SessionStartResponse**

In `src/schemas.py`, add the `DailyPageResult` class right before `SessionStartResponse` (before line 178):

```python
class DailyPageResult(BaseModel):
    page_id: str
    created: bool
    archived_count: int
```

Then update `SessionStartResponse`:

```python
class SessionStartResponse(BaseModel):
    session_id: int
    open_tasks: list[TaskContext]
    blocked_tasks: list[TaskContext]
    unsummarised_meetings: list[MeetingContext]
    sync_results: list[SourceSyncStatus]
    daily_page: DailyPageResult | None = None
```

- [ ] **Step 7: Generate alembic migration**

Run: `cd /home/agntx/Documents/repos/personal/wizard && alembic revision --autogenerate -m "add daily_page_id to wizardsession"`

Verify the generated migration adds a nullable `daily_page_id` VARCHAR column to `wizardsession`.

- [ ] **Step 8: Run the migration**

Run: `cd /home/agntx/Documents/repos/personal/wizard && alembic upgrade head`

Expected: Migration succeeds.

- [ ] **Step 9: Fix any broken config tests**

The existing `test_krisp_settings_removed` test may reference `daily_page_id`. Run all config tests:

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_config.py -v`

If any test references `daily_page_id`, update it to reference `sisu_work_page_id`.

- [ ] **Step 10: Commit**

```bash
git add src/config.py src/models.py src/schemas.py alembic/versions/ tests/test_config.py
git commit -m "feat: add sisu_work_page_id config and daily_page_id to WizardSession

Replace static daily_page_id config with sisu_work_page_id (parent page).
Daily page ID is now resolved at runtime and stored on the session."
```

---

### Task 2: NotionClient new methods

**Files:**
- Modify: `src/integrations.py:151-158` (constructor), add new methods
- Test: `tests/test_integrations.py`

**Context:** The Notion SDK provides `client.blocks.children.list(block_id=page_id)` which returns all child blocks of a page. Child pages appear as blocks with `type: "child_page"` and `child_page: {"title": "..."}`. This is more reliable than the search API for enumerating children of a specific parent.

- [ ] **Step 1: Write failing test for find_daily_page**

In `tests/test_integrations.py`, add:

```python
def test_notion_find_daily_page_returns_id_when_found():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.blocks.children.list.return_value = {
            "results": [
                {
                    "id": "page-123",
                    "type": "child_page",
                    "child_page": {"title": "Friday 11 April 2026"},
                    "archived": False,
                },
                {
                    "id": "page-old",
                    "type": "child_page",
                    "child_page": {"title": "Thursday 10 April 2026"},
                    "archived": False,
                },
            ],
            "has_more": False,
        }

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.find_daily_page("Friday 11 April 2026")

    assert result == "page-123"


def test_notion_find_daily_page_returns_none_when_not_found():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.blocks.children.list.return_value = {
            "results": [
                {
                    "id": "page-old",
                    "type": "child_page",
                    "child_page": {"title": "Thursday 10 April 2026"},
                    "archived": False,
                },
            ],
            "has_more": False,
        }

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.find_daily_page("Friday 11 April 2026")

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_find_daily_page_returns_id_when_found tests/test_integrations.py::test_notion_find_daily_page_returns_none_when_not_found -v`

Expected: FAIL — `NotionClient` constructor doesn't accept `sisu_work_page_id` yet and `find_daily_page` doesn't exist.

- [ ] **Step 3: Update NotionClient constructor and implement find_daily_page**

In `src/integrations.py`, change the constructor:

```python
class NotionClient:
    def __init__(
        self, token: str, sisu_work_page_id: str, tasks_db_id: str, meetings_db_id: str
    ):
        self._sisu_work_page_id = sisu_work_page_id
        self._tasks_db_id = tasks_db_id
        self._meetings_db_id = meetings_db_id
        self._client = NotionSdkClient(auth=token) if token else None
```

Add the helper and `find_daily_page` after the `_query_database` method:

```python
    def _list_sisu_work_children(self) -> list[dict]:
        """Return non-archived child_page blocks under the SISU Work page."""
        client = self._require_client()
        results = client.blocks.children.list(block_id=self._sisu_work_page_id)
        return [
            block
            for block in results.get("results", [])
            if block.get("type") == "child_page" and not block.get("archived", False)
        ]

    def find_daily_page(self, title: str) -> str | None:
        """Find a child page of SISU Work matching the given title."""
        try:
            for block in self._list_sisu_work_children():
                if block.get("child_page", {}).get("title") == title:
                    return block["id"]
            return None
        except Exception as e:
            logger.warning("Notion find_daily_page failed: %s", e)
            return None
```

- [ ] **Step 4: Run find_daily_page tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_find_daily_page_returns_id_when_found tests/test_integrations.py::test_notion_find_daily_page_returns_none_when_not_found -v`

Expected: PASS

- [ ] **Step 5: Write failing test for create_daily_page**

In `tests/test_integrations.py`, add:

```python
def test_notion_create_daily_page_returns_page_id():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.pages.create.return_value = {"id": "new-page-456"}

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.create_daily_page("Friday 11 April 2026")

    assert result == "new-page-456"
    mock_instance.pages.create.assert_called_once_with(
        parent={"page_id": "parent-abc"},
        properties={
            "title": [{"text": {"content": "Friday 11 April 2026"}}],
            "Session Summary": {"rich_text": [{"text": {"content": ""}}]},
        },
    )


def test_notion_create_daily_page_returns_none_on_api_error():
    from unittest.mock import MagicMock, patch

    from notion_client.errors import APIResponseError

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.pages.create.side_effect = APIResponseError(
            MagicMock(status=400), "", ""
        )

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.create_daily_page("Friday 11 April 2026")

    assert result is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_create_daily_page_returns_page_id tests/test_integrations.py::test_notion_create_daily_page_returns_none_on_api_error -v`

Expected: FAIL — `create_daily_page` doesn't exist.

- [ ] **Step 7: Implement create_daily_page**

In `src/integrations.py`, add after `find_daily_page`:

```python
    def create_daily_page(self, title: str) -> str | None:
        """Create a child page under SISU Work with title and empty Session Summary."""
        client = self._require_client()
        try:
            response = client.pages.create(
                parent={"page_id": self._sisu_work_page_id},
                properties={
                    "title": [{"text": {"content": title}}],
                    "Session Summary": {"rich_text": [{"text": {"content": ""}}]},
                },
            )
            return response.get("id")
        except APIResponseError as e:
            logger.warning("Notion create_daily_page failed: %s", e)
            return None
```

- [ ] **Step 8: Run create_daily_page tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_create_daily_page_returns_page_id tests/test_integrations.py::test_notion_create_daily_page_returns_none_on_api_error -v`

Expected: PASS

- [ ] **Step 9: Write failing test for archive_page**

In `tests/test_integrations.py`, add:

```python
def test_notion_archive_page_returns_true_on_success():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.pages.update.return_value = {"archived": True}

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.archive_page("page-old")

    assert result is True
    mock_instance.pages.update.assert_called_once_with(
        page_id="page-old", archived=True
    )


def test_notion_archive_page_returns_false_on_error():
    from unittest.mock import MagicMock, patch

    from notion_client.errors import APIResponseError

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.pages.update.side_effect = APIResponseError(
            MagicMock(status=400), "", ""
        )

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.archive_page("page-old")

    assert result is False
```

- [ ] **Step 10: Implement archive_page**

In `src/integrations.py`, add after `create_daily_page`:

```python
    def archive_page(self, page_id: str) -> bool:
        """Archive a Notion page by ID."""
        client = self._require_client()
        try:
            client.pages.update(page_id=page_id, archived=True)
            return True
        except APIResponseError as e:
            logger.warning("Notion archive_page failed: %s", e)
            return False
```

- [ ] **Step 11: Run archive_page tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_archive_page_returns_true_on_success tests/test_integrations.py::test_notion_archive_page_returns_false_on_error -v`

Expected: PASS

- [ ] **Step 12: Write failing test for ensure_daily_page**

In `tests/test_integrations.py`, add:

```python
def test_notion_ensure_daily_page_finds_existing():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.blocks.children.list.return_value = {
            "results": [
                {
                    "id": "today-page",
                    "type": "child_page",
                    "child_page": {"title": "Friday 11 April 2026"},
                    "archived": False,
                },
            ],
            "has_more": False,
        }

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        with patch("src.integrations._today_title", return_value="Friday 11 April 2026"):
            result = client.ensure_daily_page()

    assert result.page_id == "today-page"
    assert result.created is False
    assert result.archived_count == 0
    mock_instance.pages.create.assert_not_called()


def test_notion_ensure_daily_page_creates_and_archives():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        mock_instance.blocks.children.list.return_value = {
            "results": [
                {
                    "id": "old-page",
                    "type": "child_page",
                    "child_page": {"title": "Thursday 10 April 2026"},
                    "archived": False,
                },
            ],
            "has_more": False,
        }
        mock_instance.pages.create.return_value = {"id": "new-page"}
        mock_instance.pages.update.return_value = {"archived": True}

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        with patch("src.integrations._today_title", return_value="Friday 11 April 2026"):
            result = client.ensure_daily_page()

    assert result.page_id == "new-page"
    assert result.created is True
    assert result.archived_count == 1
    mock_instance.pages.update.assert_called_once_with(page_id="old-page", archived=True)
```

- [ ] **Step 13: Implement _today_title and ensure_daily_page**

In `src/integrations.py`, add the module-level helper near the top (after the imports):

```python
import datetime
```

And near the other module-level helpers (after `_extract_krisp_id`):

```python
def _today_title() -> str:
    """Build today's daily page title, e.g. 'Friday 11 April 2026'."""
    return datetime.date.today().strftime("%A %-d %B %Y")
```

On `NotionClient`, add after `archive_page`:

```python
    def ensure_daily_page(self) -> "DailyPageResult":
        """Find or create today's daily page. Archive stale daily pages."""
        from .schemas import DailyPageResult

        title = _today_title()
        children = self._list_sisu_work_children()

        page_id: str | None = None
        stale_ids: list[str] = []
        for block in children:
            block_title = block.get("child_page", {}).get("title", "")
            if block_title == title:
                page_id = block["id"]
            else:
                stale_ids.append(block["id"])

        created = False
        if page_id is None:
            page_id = self.create_daily_page(title)
            if page_id is None:
                raise ConfigurationError(
                    f"Failed to create daily page '{title}' under SISU Work"
                )
            created = True

        archived_count = 0
        for stale_id in stale_ids:
            if self.archive_page(stale_id):
                archived_count += 1

        return DailyPageResult(
            page_id=page_id, created=created, archived_count=archived_count
        )
```

- [ ] **Step 14: Run ensure_daily_page tests**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_ensure_daily_page_finds_existing tests/test_integrations.py::test_notion_ensure_daily_page_creates_and_archives -v`

Expected: PASS

- [ ] **Step 15: Run all integration tests to check for collateral**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py -v`

Expected: Some existing Notion tests may fail because `NotionClient` constructor changed from `daily_page_id` to `sisu_work_page_id`. Fix all call sites in tests — change `daily_page_id=...` to `sisu_work_page_id=...` in all `NotionClient(...)` constructor calls in `tests/test_integrations.py`.

- [ ] **Step 16: Commit**

```bash
git add src/integrations.py tests/test_integrations.py
git commit -m "feat: add daily page find/create/archive methods to NotionClient

NotionClient gains _list_sisu_work_children, find_daily_page,
create_daily_page, archive_page, and ensure_daily_page. Constructor
takes sisu_work_page_id instead of daily_page_id."
```

---

### Task 3: update_daily_page signature change + WriteBackService

**Files:**
- Modify: `src/integrations.py:325-339` (update_daily_page)
- Modify: `src/services.py:292-299` (push_session_summary)
- Test: `tests/test_integrations.py`, `tests/test_services.py`

- [ ] **Step 1: Write failing test for updated update_daily_page**

In `tests/test_integrations.py`, find the existing `test_notion_update_daily_page_*` tests (if any) or add:

```python
def test_notion_update_daily_page_with_explicit_page_id():
    from unittest.mock import MagicMock, patch

    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        from src.integrations import NotionClient

        client = NotionClient(
            token="tok",
            sisu_work_page_id="parent-abc",
            tasks_db_id="db1",
            meetings_db_id="db2",
        )
        result = client.update_daily_page("page-123", "Session went well")

    assert result is True
    mock_instance.pages.update.assert_called_once_with(
        page_id="page-123",
        properties={
            "Session Summary": {"rich_text": [{"text": {"content": "Session went well"}}]}
        },
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_update_daily_page_with_explicit_page_id -v`

Expected: FAIL — `update_daily_page` only takes `summary`, not `page_id`.

- [ ] **Step 3: Update update_daily_page signature**

In `src/integrations.py`, replace the existing `update_daily_page`:

```python
    def update_daily_page(self, page_id: str, summary: str) -> bool:
        """Update Session Summary property on a daily page."""
        client = self._require_client()

        try:
            client.pages.update(
                page_id=page_id,
                properties={
                    "Session Summary": {"rich_text": [{"text": {"content": summary}}]}
                },
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_daily_page failed: %s", e)
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_integrations.py::test_notion_update_daily_page_with_explicit_page_id -v`

Expected: PASS

- [ ] **Step 5: Write failing test for updated push_session_summary**

In `tests/test_services.py`, find the existing `test_push_session_summary` tests or add:

```python
def test_push_session_summary_uses_session_daily_page_id():
    from unittest.mock import MagicMock
    from src.models import WizardSession
    from src.services import WriteBackService

    mock_notion = MagicMock()
    mock_notion.update_daily_page.return_value = True
    service = WriteBackService(jira=MagicMock(), notion=mock_notion)

    session = WizardSession(id=1, summary="Good session", daily_page_id="page-xyz")
    result = service.push_session_summary(session)

    assert result.ok is True
    mock_notion.update_daily_page.assert_called_once_with("page-xyz", "Good session")


def test_push_session_summary_fails_without_daily_page_id():
    from unittest.mock import MagicMock
    from src.models import WizardSession
    from src.services import WriteBackService

    service = WriteBackService(jira=MagicMock(), notion=MagicMock())

    session = WizardSession(id=1, summary="Good session", daily_page_id=None)
    result = service.push_session_summary(session)

    assert result.ok is False
    assert "daily_page_id" in result.error.lower()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_services.py::test_push_session_summary_uses_session_daily_page_id tests/test_services.py::test_push_session_summary_fails_without_daily_page_id -v`

Expected: FAIL

- [ ] **Step 7: Update push_session_summary**

In `src/services.py`, replace the existing `push_session_summary`:

```python
    def push_session_summary(self, session: WizardSession) -> WriteBackStatus:
        if not session.daily_page_id:
            return WriteBackStatus(ok=False, error="Session has no daily_page_id")
        if not session.summary:
            return WriteBackStatus(ok=False, error="Session has no summary")
        page_id = session.daily_page_id
        summary = session.summary
        return self._call(
            lambda: self._notion.update_daily_page(page_id, summary),
            "WriteBack push_session_summary",
        )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_services.py::test_push_session_summary_uses_session_daily_page_id tests/test_services.py::test_push_session_summary_fails_without_daily_page_id -v`

Expected: PASS

- [ ] **Step 9: Fix any existing push_session_summary tests that broke**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_services.py -v`

If existing tests fail, update the `WizardSession` fixtures to include `daily_page_id="test-page-id"`.

- [ ] **Step 10: Commit**

```bash
git add src/integrations.py src/services.py tests/test_integrations.py tests/test_services.py
git commit -m "refactor: update_daily_page takes explicit page_id, push_session_summary uses session

update_daily_page no longer reads from instance state. push_session_summary
reads daily_page_id from the WizardSession record and passes it through."
```

---

### Task 4: session_start/session_end integration + deps wiring

**Files:**
- Modify: `src/tools.py:42-60` (session_start)
- Modify: `src/deps.py:30-38` (notion_client construction)
- Modify: `config.json`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Update deps.py — pass sisu_work_page_id**

In `src/deps.py`, change the `notion_client` function:

```python
@lru_cache
def notion_client() -> NotionClient:
    logger.debug("Creating NotionClient singleton")
    return NotionClient(
        token=settings.notion.token,
        sisu_work_page_id=settings.notion.sisu_work_page_id,
        tasks_db_id=settings.notion.tasks_db_id,
        meetings_db_id=settings.notion.meetings_db_id,
    )
```

- [ ] **Step 2: Update config.json**

In `config.json`, replace `"daily_page_id"` with `"sisu_work_page_id"`. The value should be the UUID of the SISU Work parent page (the user needs to provide this). For now use the parent page ID extracted from the existing daily page:

```json
{
  "notion": {
    "sisu_work_page_id": "",
    "tasks_db_id": "6faddf03-1642-4192-bfd0-713c97ff41d7",
    "meetings_db_id": "32100339-99d0-8070-b8f2-000b83919cde",
    "token": "ntn_bfX5410657631vQXXznkkYUod8ahXvupKG7x8CEBtlG1xW"
  }
}
```

Note: The user must fill in `sisu_work_page_id` with the actual SISU Work page UUID before running.

- [ ] **Step 3: Write failing test for session_start with daily page**

In `tests/test_tools.py`, find the existing `_patch_tools` helper pattern. Add a test:

```python
def test_session_start_resolves_daily_page(db_session):
    from unittest.mock import patch, MagicMock
    from src.schemas import DailyPageResult
    from src.tools import session_start

    mock_notion = MagicMock()
    mock_notion.ensure_daily_page.return_value = DailyPageResult(
        page_id="today-page-id", created=True, archived_count=1
    )

    with (
        patch("src.tools.get_session", mock_session(db_session)),
        patch("src.tools.sync_service") as mock_sync_svc,
        patch("src.tools.notion_client", return_value=mock_notion),
    ):
        mock_sync_svc.return_value.sync_all.return_value = []
        result = session_start()

    assert result.daily_page is not None
    assert result.daily_page.page_id == "today-page-id"
    assert result.daily_page.created is True
    assert result.daily_page.archived_count == 1
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_tools.py::test_session_start_resolves_daily_page -v`

Expected: FAIL — `session_start` doesn't call `ensure_daily_page` yet.

- [ ] **Step 5: Update session_start to call ensure_daily_page**

In `src/tools.py`, add `notion_client` to imports from deps:

```python
from .deps import meeting_repo, note_repo, notion_client, security, sync_service, task_repo, writeback
```

Update `session_start`:

```python
def session_start() -> SessionStartResponse:
    """Creates a session, syncs Jira and Notion, returns open and blocked tasks + unsummarised meetings."""
    logger.info("session_start")
    with get_session() as db:
        session = WizardSession()
        db.add(session)
        db.flush()
        db.refresh(session)
        assert session.id is not None

        sync_results = sync_service().sync_all(db)

        daily_page = None
        try:
            daily_page = notion_client().ensure_daily_page()
            session.daily_page_id = daily_page.page_id
            db.add(session)
            db.flush()
        except Exception as e:
            logger.warning("ensure_daily_page failed: %s", e)

        return SessionStartResponse(
            session_id=session.id,
            open_tasks=task_repo().get_open_task_contexts(db),
            blocked_tasks=task_repo().get_blocked_task_contexts(db),
            unsummarised_meetings=meeting_repo().get_unsummarised_contexts(db),
            sync_results=sync_results,
            daily_page=daily_page,
        )
```

- [ ] **Step 6: Run session_start test**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_tools.py::test_session_start_resolves_daily_page -v`

Expected: PASS

- [ ] **Step 7: Fix any existing session_start/session_end tests that broke**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_tools.py -v`

Existing `session_start` tests may need a `notion_client` mock added. Existing `session_end` tests may need `daily_page_id` set on the session fixture.

- [ ] **Step 8: Run the full test suite**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest -v`

Expected: All 169+ tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/tools.py src/deps.py config.json tests/test_tools.py
git commit -m "feat: session_start resolves daily page, session_end uses session page ID

session_start calls ensure_daily_page() to find or create today's
Notion daily page, stores the ID on WizardSession, and archives stale
pages. session_end writes to the session's resolved page ID."
```

---

## Verification

After all tasks, run the full suite and do a manual smoke test:

```bash
# Full test suite
cd /home/agntx/Documents/repos/personal/wizard && python -m pytest -v

# Manual: set sisu_work_page_id in config.json to the real SISU Work page UUID
# Start the server and call session_start — verify daily page appears in Notion
# Call session_end — verify summary writes to the daily page
```
