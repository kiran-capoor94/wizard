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


# ============================================================================
# NotionClient Tests
# ============================================================================

def make_notion_client(
    token="tok",
    daily_page_id="page-daily",
    tasks_db_id="db-tasks",
    meetings_db_id="db-meetings"
):
    from src.integrations import NotionClient
    return NotionClient(
        token=token,
        daily_page_id=daily_page_id,
        tasks_db_id=tasks_db_id,
        meetings_db_id=meetings_db_id
    )


# ---- fetch_tasks tests ----

def test_notion_fetch_tasks_returns_list_of_dicts():
    """fetch_tasks should return list with notion_id, name, status, priority, due_date, jira_url, jira_key"""
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
    assert tasks[0]["notion_id"] == "task-uuid-1"
    assert tasks[0]["name"] == "Implement auth"
    assert tasks[0]["status"] == "In Progress"
    assert tasks[0]["priority"] == "High"
    assert tasks[0]["due_date"] == "2026-04-15"
    assert tasks[0]["jira_url"] == "https://org.atlassian.net/browse/ENG-123"
    assert tasks[0]["jira_key"] == "ENG-123"


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
    assert tasks[0]["notion_id"] == "task-uuid-2"
    assert tasks[0]["name"] == "Task with minimal props"
    assert tasks[0]["status"] is None
    assert tasks[0]["priority"] is None
    assert tasks[0]["due_date"] is None
    assert tasks[0]["jira_url"] is None
    assert tasks[0]["jira_key"] is None


def test_notion_fetch_tasks_raises_error_without_token():
    """fetch_tasks should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
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

def test_notion_fetch_meetings_returns_list_of_dicts():
    """fetch_meetings should return list with notion_id, title, categories, summary, krisp_url, date"""
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
    assert meetings[0]["notion_id"] == "meeting-uuid-1"
    assert meetings[0]["title"] == "Sprint Planning"
    assert meetings[0]["categories"] == ["Planning", "Standup"]
    assert meetings[0]["summary"] == "Discussed Q2 roadmap"
    assert meetings[0]["krisp_url"] == "https://krisp.ai/m/abc123"
    assert meetings[0]["date"] == "2026-04-10"


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
    assert meetings[0]["notion_id"] == "meeting-uuid-2"
    assert meetings[0]["title"] == "Minimal meeting"
    assert meetings[0]["categories"] == []
    assert meetings[0]["summary"] is None
    assert meetings[0]["krisp_url"] is None
    assert meetings[0]["date"] is None


def test_notion_fetch_meetings_raises_error_without_token():
    """fetch_meetings should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
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
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
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
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
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
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
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
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_meeting_summary("meeting-id", "Summary")


# ---- update_daily_page tests ----

def test_notion_update_daily_page_returns_true_on_success():
    """update_daily_page should return True on success"""
    client = make_notion_client()

    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_daily_page("session summary text")

    assert result is True


def test_notion_update_daily_page_returns_false_on_api_error():
    """update_daily_page should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("src.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_daily_page("summary")

    assert result is False


def test_notion_update_daily_page_raises_error_without_token():
    """update_daily_page should raise ConfigurationError if no token"""
    from src.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_id="p1", tasks_db_id="db1", meetings_db_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_daily_page("summary")


# ---- Helper function tests ----

def test_extract_jira_key_from_url():
    """_extract_jira_key should extract issue key from Jira URL"""
    from src.integrations import _extract_jira_key

    assert _extract_jira_key("https://org.atlassian.net/browse/ENG-123") == "ENG-123"
    assert _extract_jira_key("https://jira.company.com/browse/PROJ-456") == "PROJ-456"
    assert _extract_jira_key(None) is None
    assert _extract_jira_key("") is None
    assert _extract_jira_key("not-a-url") is None


def test_get_title():
    """_get_title should extract plain text from title property"""
    from src.integrations import _get_title

    props = {
        "Name": {"title": [{"plain_text": "Test Title"}]}
    }
    assert _get_title(props, "Name") == "Test Title"

    # Missing property
    assert _get_title(props, "Missing") is None

    # Empty title array
    props2 = {"Name": {"title": []}}
    assert _get_title(props2, "Name") is None


def test_get_rich_text():
    """_get_rich_text should extract plain text from rich_text property"""
    from src.integrations import _get_rich_text

    props = {
        "Summary": {"rich_text": [{"plain_text": "Test summary"}]}
    }
    assert _get_rich_text(props, "Summary") == "Test summary"

    # Missing property
    assert _get_rich_text(props, "Missing") is None

    # Empty rich text array
    props2 = {"Summary": {"rich_text": []}}
    assert _get_rich_text(props2, "Summary") is None


def test_get_select():
    """_get_select should extract name from select property"""
    from src.integrations import _get_select

    props = {
        "Status": {"select": {"name": "In Progress"}}
    }
    assert _get_select(props, "Status") == "In Progress"

    # Missing property
    assert _get_select(props, "Missing") is None

    # Null select
    props2 = {"Status": {"select": None}}
    assert _get_select(props2, "Status") is None


def test_get_multi_select():
    """_get_multi_select should extract list of names from multi_select property"""
    from src.integrations import _get_multi_select

    props = {
        "Tags": {"multi_select": [{"name": "Tag1"}, {"name": "Tag2"}]}
    }
    assert _get_multi_select(props, "Tags") == ["Tag1", "Tag2"]

    # Missing property
    assert _get_multi_select(props, "Missing") is None

    # Empty multi_select
    props2 = {"Tags": {"multi_select": []}}
    assert _get_multi_select(props2, "Tags") == []


def test_get_url():
    """_get_url should extract URL"""
    from src.integrations import _get_url

    props = {
        "Link": {"url": "https://example.com"}
    }
    assert _get_url(props, "Link") == "https://example.com"

    # Missing property
    assert _get_url(props, "Missing") is None

    # Null URL
    props2 = {"Link": {"url": None}}
    assert _get_url(props2, "Link") is None


def test_get_date_start():
    """_get_date_start should extract start date from date property"""
    from src.integrations import _get_date_start

    props = {
        "Due": {"date": {"start": "2026-04-15"}}
    }
    assert _get_date_start(props, "Due") == "2026-04-15"

    # Missing property
    assert _get_date_start(props, "Missing") is None

    # Null date
    props2 = {"Due": {"date": None}}
    assert _get_date_start(props2, "Due") is None


def test_get_status():
    """_get_status should extract name from status property"""
    from src.integrations import _get_status

    props = {
        "State": {"status": {"name": "Active"}}
    }
    assert _get_status(props, "State") == "Active"

    # Missing property
    assert _get_status(props, "Missing") is None

    # Null status
    props2 = {"State": {"status": None}}
    assert _get_status(props2, "State") is None
