import pytest
import httpx
import respx
from unittest.mock import patch, MagicMock
from notion_client.errors import APIResponseError

from src.schemas import (
    NotionTitle, NotionRichText, NotionSelect, NotionMultiSelect,
    NotionUrl, NotionDate, NotionStatus,
)


class TestNotionTitle:
    def test_extracts_plain_text(self):
        prop = {"title": [{"plain_text": "Test Title"}]}
        assert NotionTitle.model_validate(prop).text == "Test Title"

    def test_returns_none_for_empty(self):
        assert NotionTitle.model_validate({"title": []}).text is None

    def test_returns_none_for_missing(self):
        assert NotionTitle.model_validate({}).text is None


class TestNotionRichText:
    def test_extracts_plain_text(self):
        prop = {"rich_text": [{"plain_text": "Test summary"}]}
        assert NotionRichText.model_validate(prop).text == "Test summary"

    def test_returns_none_for_empty(self):
        assert NotionRichText.model_validate({"rich_text": []}).text is None


class TestNotionSelect:
    def test_extracts_name(self):
        prop = {"select": {"name": "In Progress"}}
        assert NotionSelect.model_validate(prop).name == "In Progress"

    def test_returns_none_for_null(self):
        assert NotionSelect.model_validate({"select": None}).name is None


class TestNotionMultiSelect:
    def test_extracts_names(self):
        prop = {"multi_select": [{"name": "Tag1"}, {"name": "Tag2"}]}
        assert NotionMultiSelect.model_validate(prop).names == ["Tag1", "Tag2"]

    def test_returns_empty_for_empty(self):
        assert NotionMultiSelect.model_validate({"multi_select": []}).names == []


class TestNotionUrl:
    def test_extracts_url(self):
        prop = {"url": "https://example.com"}
        assert NotionUrl.model_validate(prop).url == "https://example.com"

    def test_returns_none_for_null(self):
        assert NotionUrl.model_validate({"url": None}).url is None


class TestNotionDate:
    def test_extracts_start(self):
        prop = {"date": {"start": "2026-04-15"}}
        assert NotionDate.model_validate(prop).start == "2026-04-15"

    def test_returns_none_for_null(self):
        assert NotionDate.model_validate({"date": None}).start is None


class TestNotionStatus:
    def test_extracts_name(self):
        prop = {"status": {"name": "Active"}}
        assert NotionStatus.model_validate(prop).name == "Active"

    def test_returns_none_for_null(self):
        assert NotionStatus.model_validate({"status": None}).name is None


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


@respx.mock
def test_jira_fetch_open_tasks_returns_list():
    respx.post("https://jira.example.com/rest/api/3/search/jql").mock(
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
                            "self": "https://jira.example.com/rest/api/3/issue/ENG-1",
                        },
                    }
                ]
            },
        )
    )
    client = make_jira_client()
    tasks = client.fetch_open_tasks()

    assert len(tasks) == 1
    assert tasks[0].key == "ENG-1"
    assert tasks[0].summary == "Fix login"
    assert tasks[0].status == "In Progress"
    assert tasks[0].priority == "High"
    assert tasks[0].issue_type == "Bug"


@respx.mock
def test_jira_fetch_open_tasks_returns_empty_on_http_error():
    respx.post("https://jira.example.com/rest/api/3/search/jql").mock(
        return_value=httpx.Response(500)
    )
    client = make_jira_client()
    tasks = client.fetch_open_tasks()

    assert tasks == []


@respx.mock
def test_jira_update_task_status_returns_true_on_success():
    respx.get("https://jira.example.com/rest/api/3/issue/ENG-1/transitions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transitions": [
                    {"id": "31", "name": "Done"},
                ]
            },
        )
    )
    respx.post("https://jira.example.com/rest/api/3/issue/ENG-1/transitions").mock(
        return_value=httpx.Response(204)
    )
    client = make_jira_client()
    result = client.update_task_status("ENG-1", "done")

    assert result is True


@respx.mock
def test_jira_update_task_status_returns_false_on_http_error():
    respx.get("https://jira.example.com/rest/api/3/issue/ENG-1/transitions").mock(
        return_value=httpx.Response(
            200,
            json={
                "transitions": [
                    {"id": "31", "name": "Done"},
                ]
            },
        )
    )
    respx.post("https://jira.example.com/rest/api/3/issue/ENG-1/transitions").mock(
        return_value=httpx.Response(500)
    )
    client = make_jira_client()
    result = client.update_task_status("ENG-1", "done")

    assert result is False


# ============================================================================
# NotionClient Tests
# ============================================================================

def make_notion_client(
    token="tok",
    sisu_work_page_id="parent-abc",
    tasks_db_id="db-tasks",
    meetings_db_id="db-meetings"
):
    from src.integrations import NotionClient
    return NotionClient(
        token=token,
        sisu_work_page_id=sisu_work_page_id,
        tasks_db_id=tasks_db_id,
        meetings_db_id=meetings_db_id
    )


# ---- fetch_tasks tests ----

def test_notion_fetch_tasks_returns_typed_models():
    """fetch_tasks should return list of NotionTaskData with notion_id, name, status, priority, due_date, jira_url, jira_key"""
    client = make_notion_client()

    mock_pages = [
        {
            "id": "task-uuid-1",
            "properties": {
                "Task": {"title": [{"plain_text": "Implement auth"}]},
                "Status": {"status": {"name": "In Progress"}},
                "Priority": {"select": {"name": "High"}},
                "Due date": {"date": {"start": "2026-04-15"}},
                "Jira": {"url": "https://org.atlassian.net/browse/ENG-123"},
            }
        }
    ]

    with patch("src.integrations.collect_paginated_api", return_value=mock_pages):
        client = make_notion_client()
        tasks = client.fetch_tasks()

    assert len(tasks) == 1
    assert tasks[0].notion_id == "task-uuid-1"
    assert tasks[0].name == "Implement auth"
    assert tasks[0].status == "In Progress"
    assert tasks[0].priority == "High"
    assert tasks[0].due_date == "2026-04-15"
    assert tasks[0].jira_url == "https://org.atlassian.net/browse/ENG-123"
    assert tasks[0].jira_key == "ENG-123"


def test_notion_fetch_tasks_handles_missing_properties():
    """fetch_tasks should use None for missing optional properties"""
    mock_pages = [
        {
            "id": "task-uuid-2",
            "properties": {
                "Task": {"title": [{"plain_text": "Task with minimal props"}]},
                "Status": {"status": None},
                "Priority": {"select": None},
                "Due date": {"date": None},
                "Jira": {"url": None},
            }
        }
    ]

    with patch("src.integrations.collect_paginated_api", return_value=mock_pages):
        client = make_notion_client()
        tasks = client.fetch_tasks()

    assert len(tasks) == 1
    assert tasks[0].notion_id == "task-uuid-2"
    assert tasks[0].name == "Task with minimal props"
    assert tasks[0].status is None
    assert tasks[0].priority is None
    assert tasks[0].due_date is None
    assert tasks[0].jira_url is None
    assert tasks[0].jira_key is None


def test_notion_fetch_tasks_raises_error_without_token():
    """fetch_tasks should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.fetch_tasks()


def test_notion_fetch_tasks_returns_empty_on_api_error():
    """fetch_tasks should return [] on Notion API error (non-fatal)"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.collect_paginated_api", side_effect=error):
        client = make_notion_client()
        tasks = client.fetch_tasks()

    assert tasks == []


# ---- fetch_meetings tests ----

def test_notion_fetch_meetings_returns_typed_models():
    """fetch_meetings should return list of NotionMeetingData with notion_id, title, categories, summary, krisp_url, date"""
    mock_pages = [
        {
            "id": "meeting-uuid-1",
            "properties": {
                "Meeting name": {"title": [{"plain_text": "Sprint Planning"}]},
                "Category": {
                    "multi_select": [
                        {"name": "Planning"},
                        {"name": "Standup"}
                    ]
                },
                "Summary": {"rich_text": [{"plain_text": "Discussed Q2 roadmap"}]},
                "Krisp URL": {"url": "https://krisp.ai/m/abc123"},
                "Date": {"date": {"start": "2026-04-10"}},
            }
        }
    ]

    with patch("src.integrations.collect_paginated_api", return_value=mock_pages):
        client = make_notion_client()
        meetings = client.fetch_meetings()

    assert len(meetings) == 1
    assert meetings[0].notion_id == "meeting-uuid-1"
    assert meetings[0].title == "Sprint Planning"
    assert meetings[0].categories == ["Planning", "Standup"]
    assert meetings[0].summary == "Discussed Q2 roadmap"
    assert meetings[0].krisp_url == "https://krisp.ai/m/abc123"
    assert meetings[0].date == "2026-04-10"


def test_notion_fetch_meetings_handles_missing_properties():
    """fetch_meetings should use None/[] for missing optional properties"""
    mock_pages = [
        {
            "id": "meeting-uuid-2",
            "properties": {
                "Meeting name": {"title": [{"plain_text": "Minimal meeting"}]},
                "Category": {"multi_select": []},
                "Summary": {"rich_text": []},
                "Krisp URL": {"url": None},
                "Date": {"date": None},
            }
        }
    ]

    with patch("src.integrations.collect_paginated_api", return_value=mock_pages):
        client = make_notion_client()
        meetings = client.fetch_meetings()

    assert len(meetings) == 1
    assert meetings[0].notion_id == "meeting-uuid-2"
    assert meetings[0].title == "Minimal meeting"
    assert meetings[0].categories == []
    assert meetings[0].summary is None
    assert meetings[0].krisp_url is None
    assert meetings[0].date is None


def test_notion_fetch_meetings_raises_error_without_token():
    """fetch_meetings should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.fetch_meetings()


def test_notion_fetch_meetings_returns_empty_on_api_error():
    """fetch_meetings should return [] on Notion API error (non-fatal)"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.collect_paginated_api", side_effect=error):
        client = make_notion_client()
        meetings = client.fetch_meetings()

    assert meetings == []


# ---- create_task_page tests ----

def test_notion_create_task_page_returns_page_id():
    """create_task_page should return page_id on success"""
    client = make_notion_client()

    mock_response = {
        "id": "new-task-uuid",
        "object": "page"
    }

    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.return_value = mock_response

        client = make_notion_client()
        page_id = client.create_task_page(
            name="New task",
            status="In Progress",
            priority="High",
            jira_url="https://org.atlassian.net/browse/ENG-999",
            due_date="2026-04-20"
        )

    assert page_id == "new-task-uuid"


def test_notion_create_task_page_requires_name_and_status():
    """create_task_page requires name and status"""
    client = make_notion_client()

    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.return_value = {"id": "test-id"}

        client = make_notion_client()
        client.create_task_page(
            name="Task",
            status="Backlog"
        )

    # Should call with proper structure
    mock_client_instance.pages.create.assert_called_once()
    call_args = mock_client_instance.pages.create.call_args
    assert "parent" in call_args.kwargs
    assert "properties" in call_args.kwargs


def test_notion_create_task_page_returns_none_on_api_error():
    """create_task_page should return None on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.side_effect = error

        client = make_notion_client()
        page_id = client.create_task_page(name="Task", status="Backlog")

    assert page_id is None


def test_notion_create_task_page_raises_error_without_token():
    """create_task_page should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.create_task_page(name="Task", status="Backlog")


# ---- create_meeting_page tests ----

def test_notion_create_meeting_page_returns_page_id():
    """create_meeting_page should return page_id on success"""
    client = make_notion_client()

    mock_response = {
        "id": "new-meeting-uuid",
        "object": "page"
    }

    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.return_value = mock_response

        client = make_notion_client()
        page_id = client.create_meeting_page(
            title="Q2 Planning",
            category="Planning",
            krisp_url="https://krisp.ai/m/xyz",
            summary="Discussed roadmap"
        )

    assert page_id == "new-meeting-uuid"


def test_notion_create_meeting_page_requires_title_and_category():
    """create_meeting_page requires title and category"""
    client = make_notion_client()

    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.return_value = {"id": "test-id"}

        client = make_notion_client()
        client.create_meeting_page(
            title="Meeting",
            category="Standup"
        )

    # Should call with proper structure
    mock_client_instance.pages.create.assert_called_once()
    call_args = mock_client_instance.pages.create.call_args
    assert "parent" in call_args.kwargs
    assert "properties" in call_args.kwargs


def test_notion_create_meeting_page_returns_none_on_api_error():
    """create_meeting_page should return None on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.create.side_effect = error

        client = make_notion_client()
        page_id = client.create_meeting_page(title="Meeting", category="Planning")

    assert page_id is None


def test_notion_create_meeting_page_raises_error_without_token():
    """create_meeting_page should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.create_meeting_page(title="Meeting", category="Planning")


# ---- update_task_status tests ----

def test_notion_update_task_status_returns_true_on_success():
    """update_task_status should return True on success"""
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_task_status("task-id", "Done")

    assert result is True


def test_notion_update_task_status_returns_false_on_api_error():
    """update_task_status should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_task_status("task-id", "Done")

    assert result is False


def test_notion_update_task_status_raises_error_without_token():
    """update_task_status should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_task_status("task-id", "Done")


# ---- update_meeting_summary tests ----

def test_notion_update_meeting_summary_returns_true_on_success():
    """update_meeting_summary should return True on success"""
    client = make_notion_client()

    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_meeting_summary("meeting-id", "Summary text")

    assert result is True


def test_notion_update_meeting_summary_returns_false_on_api_error():
    """update_meeting_summary should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_meeting_summary("meeting-id", "Summary text")

    assert result is False


def test_notion_update_meeting_summary_raises_error_without_token():
    """update_meeting_summary should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_meeting_summary("meeting-id", "Summary")


# ---- update_daily_page tests ----

def test_notion_update_daily_page_returns_true_on_success():
    """update_daily_page should return True on success"""
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_daily_page("page-123", "session summary text")

    assert result is True


def test_notion_update_daily_page_returns_false_on_api_error():
    """update_daily_page should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_daily_page("page-123", "summary")

    assert result is False


def test_notion_update_daily_page_raises_error_without_token():
    """update_daily_page should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", sisu_work_page_id="parent-abc", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_daily_page("page-123", "summary")


def test_notion_update_daily_page_with_explicit_page_id():
    """update_daily_page should call pages.update with the given page_id, not instance state"""
    from unittest.mock import MagicMock, patch
    with patch("src.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        from src.integrations import NotionClient
        client = NotionClient(
            token="tok", sisu_work_page_id="parent-abc",
            tasks_db_id="db1", meetings_db_id="db2",
        )
        result = client.update_daily_page("page-123", "Session went well")
    assert result is True
    mock_instance.pages.update.assert_called_once_with(
        page_id="page-123",
        properties={"Session Summary": {"rich_text": [{"text": {"content": "Session went well"}}]}},
    )


def test_extract_jira_key_from_url():
    """_extract_jira_key should extract issue key from Jira URL"""
    from src.integrations import _extract_jira_key

    assert _extract_jira_key("https://org.atlassian.net/browse/ENG-123") == "ENG-123"
    assert _extract_jira_key("https://jira.company.com/browse/PROJ-456") == "PROJ-456"
    assert _extract_jira_key(None) is None
    assert _extract_jira_key("") is None
    assert _extract_jira_key("not-a-url") is None


def test_extract_krisp_id_from_url():
    """_extract_krisp_id should extract last path segment from Krisp URL"""
    from src.integrations import _extract_krisp_id

    assert _extract_krisp_id("https://krisp.ai/m/abc123") == "abc123"
    assert _extract_krisp_id("https://krisp.ai/m/abc123/") == "abc123"
    assert _extract_krisp_id("https://krisp.ai/m/abc123?foo=bar") == "abc123"
    assert _extract_krisp_id(None) is None
    assert _extract_krisp_id("") is None


# ============================================================================
# NotionClient — daily page methods
# ============================================================================

def _make_child_page_block(block_id: str, title: str, archived: bool = False) -> dict:
    return {
        "id": block_id,
        "type": "child_page",
        "child_page": {"title": title},
        "archived": archived,
    }


def test_notion_find_daily_page_returns_id_when_found():
    """find_daily_page returns the page_id of the matching child page."""
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.blocks.children.list.return_value = {
            "results": [
                _make_child_page_block("id-other", "Wednesday 8 April 2026"),
                _make_child_page_block("id-match", "Friday 11 April 2026"),
            ]
        }

        client = make_notion_client()
        result = client.find_daily_page("Friday 11 April 2026")

    assert result == "id-match"


def test_notion_find_daily_page_returns_none_when_not_found():
    """find_daily_page returns None when no child page matches the title."""
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.blocks.children.list.return_value = {
            "results": [
                _make_child_page_block("id-other", "Wednesday 8 April 2026"),
                _make_child_page_block("id-another", "Thursday 9 April 2026"),
            ]
        }

        client = make_notion_client()
        result = client.find_daily_page("Friday 11 April 2026")

    assert result is None


def test_notion_create_daily_page_returns_page_id():
    """create_daily_page calls pages.create with correct args and returns page_id."""
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.pages.create.return_value = {"id": "new-daily-id"}

        client = make_notion_client()
        result = client.create_daily_page("Friday 11 April 2026")

    assert result == "new-daily-id"
    mock_instance.pages.create.assert_called_once_with(
        parent={"page_id": "parent-abc"},
        properties={
            "title": [{"text": {"content": "Friday 11 April 2026"}}],
            "Session Summary": {"rich_text": [{"text": {"content": ""}}]},
        },
    )


def test_notion_create_daily_page_returns_none_on_api_error():
    """create_daily_page returns None on APIResponseError."""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.pages.create.side_effect = error

        client = make_notion_client()
        result = client.create_daily_page("Friday 11 April 2026")

    assert result is None


def test_notion_archive_page_returns_true_on_success():
    """archive_page calls pages.update with archived=True and returns True."""
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.archive_page("some-page-id")

    assert result is True
    mock_instance.pages.update.assert_called_once_with(
        page_id="some-page-id", archived=True
    )


def test_notion_archive_page_returns_false_on_error():
    """archive_page returns False on APIResponseError."""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.archive_page("some-page-id")

    assert result is False


def test_notion_ensure_daily_page_finds_existing():
    """ensure_daily_page returns existing page without creating, archived_count=0."""
    with patch("src.integrations._today_title", return_value="Friday 11 April 2026"):
        with patch("src.integrations.NotionSdkClient") as mock_notion_class:
            mock_instance = MagicMock()
            mock_notion_class.return_value = mock_instance
            mock_instance.blocks.children.list.return_value = {
                "results": [
                    _make_child_page_block("existing-daily-id", "Friday 11 April 2026"),
                ]
            }

            client = make_notion_client()
            result = client.ensure_daily_page()

    assert result.page_id == "existing-daily-id"
    assert result.created is False
    assert result.archived_count == 0
    mock_instance.pages.create.assert_not_called()


def test_notion_ensure_daily_page_creates_and_archives():
    """ensure_daily_page creates today's page and archives 1 stale page."""
    with patch("src.integrations._today_title", return_value="Friday 11 April 2026"):
        with patch("src.integrations.NotionSdkClient") as mock_notion_class:
            mock_instance = MagicMock()
            mock_notion_class.return_value = mock_instance
            mock_instance.blocks.children.list.return_value = {
                "results": [
                    _make_child_page_block("stale-id", "Thursday 10 April 2026"),
                ]
            }
            mock_instance.pages.create.return_value = {"id": "new-daily-id"}
            mock_instance.pages.update.return_value = {}

            client = make_notion_client()
            result = client.ensure_daily_page()

    assert result.page_id == "new-daily-id"
    assert result.created is True
    assert result.archived_count == 1
    mock_instance.pages.update.assert_called_once_with(
        page_id="stale-id", archived=True
    )
