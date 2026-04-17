"""Tests for NotionClient fetch operations."""

from unittest.mock import patch

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


# ---- fetch_tasks tests ----

def test_notion_fetch_tasks_returns_typed_models():
    """fetch_tasks should return list of NotionTaskData with notion_id, name, status, priority, due_date, jira_url, jira_key"""
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

    with patch("wizard.integrations.collect_paginated_api", return_value=mock_pages):
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

    with patch("wizard.integrations.collect_paginated_api", return_value=mock_pages):
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
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.fetch_tasks()


def test_notion_fetch_tasks_returns_empty_on_api_error():
    """fetch_tasks should return [] on Notion API error (non-fatal)"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.collect_paginated_api", side_effect=error):
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

    with patch("wizard.integrations.collect_paginated_api", return_value=mock_pages):
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

    with patch("wizard.integrations.collect_paginated_api", return_value=mock_pages):
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
    from wizard.integrations import ConfigurationError, NotionClient
    client = NotionClient(token="", daily_page_parent_id="parent-abc", tasks_ds_id="db1", meetings_ds_id="db2")
    with pytest.raises(ConfigurationError):
        client.fetch_meetings()


def test_notion_fetch_meetings_returns_empty_on_api_error():
    """fetch_meetings should return [] on Notion API error (non-fatal)"""
    error = APIResponseError("internal_server_error", 500, "Server error", httpx.Headers(), "")
    with patch("wizard.integrations.collect_paginated_api", side_effect=error):
        client = make_notion_client()
        meetings = client.fetch_meetings()

    assert meetings == []


def test_notion_fetch_meetings_uses_schema_meeting_category():
    """fetch_meetings reads category using the schema meeting_category field name."""
    from wizard.config import NotionSchemaSettings
    schema = NotionSchemaSettings(meeting_category="Meeting Type")
    mock_pages = [
        {
            "id": "m-1",
            "properties": {
                "Meeting name": {"title": [{"plain_text": "Sprint Retro"}]},
                "Meeting Type": {"multi_select": [{"name": "Retro"}]},
                "Summary": {"rich_text": []},
                "Krisp URL": {"url": None},
                "Date": {"date": None},
            },
        }
    ]
    with patch("wizard.integrations.collect_paginated_api", return_value=mock_pages):
        client = make_notion_client(schema=schema)
        meetings = client.fetch_meetings()

    assert len(meetings) == 1
    assert meetings[0].categories == ["Retro"]


# ---- schema wiring tests ----

def test_notion_client_uses_schema_for_task_name():
    from wizard.config import NotionSchemaSettings
    from wizard.integrations import NotionClient

    schema = NotionSchemaSettings(task_name="My Task")
    client = NotionClient(
        token="tok",
        daily_page_parent_id="p",
        tasks_ds_id="t",
        meetings_ds_id="m",
        schema=schema,
    )
    page = {
        "id": "page-1",
        "properties": {
            "My Task": {"type": "title", "title": [{"plain_text": "Test Task"}]},
            "Status": {"type": "status", "status": {"name": "In Progress"}},
            "Priority": {"type": "select", "select": {"name": "High"}},
            "Due date": {"type": "date", "date": None},
            "Jira": {"type": "url", "url": None},
        },
    }
    with patch("wizard.integrations.collect_paginated_api", return_value=[page]):
        tasks = client.fetch_tasks()
    assert len(tasks) == 1
    assert tasks[0].name == "Test Task"


def test_notion_client_uses_schema_for_meeting_url():
    from wizard.config import NotionSchemaSettings
    from wizard.integrations import NotionClient

    schema = NotionSchemaSettings(meeting_url="Fathom URL")
    client = NotionClient(
        token="tok",
        daily_page_parent_id="p",
        tasks_ds_id="t",
        meetings_ds_id="m",
        schema=schema,
    )
    page = {
        "id": "page-2",
        "properties": {
            "Meeting name": {"type": "title", "title": [{"plain_text": "Standup"}]},
            "Category": {"type": "multi_select", "multi_select": []},
            "Summary": {"type": "rich_text", "rich_text": []},
            "Fathom URL": {"type": "url", "url": "https://fathom.video/123"},
            "Date": {"type": "date", "date": None},
        },
    }
    with patch("wizard.integrations.collect_paginated_api", return_value=[page]):
        meetings = client.fetch_meetings()
    assert len(meetings) == 1
    assert meetings[0].krisp_url == "https://fathom.video/123"
