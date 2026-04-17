"""Tests for NotionClient write/update operations."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from notion_client.errors import APIResponseError


def make_notion_client(
    token="tok",
    daily_page_parent_id="parent-abc",
    tasks_ds_id="db-tasks",
    meetings_ds_id="db-meetings",
    schema=None,
):
    from wizard.integrations import NotionClient
    return NotionClient(
        token=token,
        daily_page_parent_id=daily_page_parent_id,
        tasks_ds_id=tasks_ds_id,
        meetings_ds_id=meetings_ds_id,
        schema=schema
    )


# ---- create_task_page tests ----

def test_notion_create_task_page_returns_page_id():
    """create_task_page should return page_id on success"""
    mock_response = {
        "id": "new-task-uuid",
        "object": "page"
    }

    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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


def test_notion_create_task_page_raises_error_without_token():
    """create_task_page should raise ConfigurationError if no token"""
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.create_task_page(name="Task", status="Backlog")


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


# ---- create_meeting_page tests ----

def test_notion_create_meeting_page_returns_page_id():
    """create_meeting_page should return page_id on success"""
    mock_response = {
        "id": "new-meeting-uuid",
        "object": "page"
    }

    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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


def test_notion_create_meeting_page_raises_error_without_token():
    """create_meeting_page should raise ConfigurationError if no token"""
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.create_meeting_page(title="Meeting", category="Planning")


def test_notion_create_meeting_page_uses_schema_meeting_category():
    """create_meeting_page uses schema.meeting_category as the property key."""
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings(meeting_category="Meeting Type")

    with patch("wizard.integrations.NotionSdkClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.pages.create.return_value = {"id": "new-page"}

        client = make_notion_client(schema=schema)
        page_id = client.create_meeting_page(title="Standup", category="Standup")

    assert page_id == "new-page"
    call_props = mock_instance.pages.create.call_args.kwargs["properties"]
    assert "Meeting Type" in call_props
    assert "Category" not in call_props


# ---- update_task_status tests ----

def test_notion_update_task_status_returns_true_on_success():
    """update_task_status should return True on success"""
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_task_status("task-id", "Done")

    assert result is True


def test_notion_update_task_status_returns_false_on_api_error():
    """update_task_status should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_task_status("task-id", "Done")

    assert result is False


def test_notion_update_task_status_raises_error_without_token():
    """update_task_status should raise ConfigurationError if no token"""
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_task_status("task-id", "Done")


def test_notion_update_task_status_uses_schema_property_name():
    """update_task_status must use schema.task_status as property key, not hardcoded 'Status'."""
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings(task_status="State")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client(schema=schema)
        client.update_task_status("task-id", "Done")

    props = mock_client_instance.pages.update.call_args.kwargs["properties"]
    assert "State" in props
    assert "Status" not in props


# ---- update_meeting_summary tests ----

def test_notion_update_meeting_summary_returns_true_on_success():
    """update_meeting_summary should return True on success"""
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_meeting_summary("meeting-id", "Summary text")

    assert result is True


def test_notion_update_meeting_summary_returns_false_on_api_error():
    """update_meeting_summary should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_meeting_summary("meeting-id", "Summary text")

    assert result is False


def test_notion_update_meeting_summary_raises_error_without_token():
    """update_meeting_summary should raise ConfigurationError if no token"""
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_meeting_summary("meeting-id", "Summary")


def test_notion_update_meeting_summary_uses_schema_property_name():
    """update_meeting_summary must use schema.meeting_summary as property key, not hardcoded 'Summary'."""
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings(meeting_summary="Notes")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client(schema=schema)
        client.update_meeting_summary("meeting-id", "Great sprint")

    props = mock_client_instance.pages.update.call_args.kwargs["properties"]
    assert "Notes" in props
    assert "Summary" not in props


# ---- update_daily_page tests ----

def test_notion_update_daily_page_returns_true_on_success():
    """update_daily_page should return True on success"""
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.return_value = {}

        client = make_notion_client()
        result = client.update_daily_page("page-123", "session summary text")

    assert result is True


def test_notion_update_daily_page_returns_false_on_api_error():
    """update_daily_page should return False on Notion API error"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_client_instance = MagicMock()
        mock_notion_class.return_value = mock_client_instance
        mock_client_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.update_daily_page("page-123", "summary")

    assert result is False


def test_notion_update_daily_page_raises_error_without_token():
    """update_daily_page should raise ConfigurationError if no token"""
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.update_daily_page("page-123", "summary")


def test_notion_update_daily_page_with_explicit_page_id():
    """update_daily_page should call pages.update with the given page_id, not instance state"""
    with patch("wizard.integrations.NotionSdkClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        from wizard.integrations import NotionClient
        client = NotionClient(
            token="tok", daily_page_parent_id="parent-abc",
            tasks_ds_id="db1", meetings_ds_id="db2",
        )
        result = client.update_daily_page("page-123", "Session went well")
    assert result is True
    mock_instance.pages.update.assert_called_once_with(
        page_id="page-123",
        properties={"Session Summary": {"rich_text": [{"text": {"content": "Session went well"}}]}},
    )
