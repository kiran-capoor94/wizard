import pytest
import httpx
from unittest.mock import patch, MagicMock


def make_jira_client(base_url="https://jira.example.com", token="tok", project_key="ENG"):
    from src.integrations import JiraClient
    return JiraClient(base_url=base_url, token=token, project_key=project_key)


def test_jira_raises_configuration_error_when_no_token():
    from src.integrations import JiraClient, ConfigurationError
    client = JiraClient(base_url="https://jira.example.com", token="", project_key="ENG")
    with pytest.raises(ConfigurationError):
        client.fetch_open_tasks()


def test_jira_fetch_open_tasks_returns_list():
    client = make_jira_client()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "issues": [
            {
                "key": "ENG-1",
                "fields": {
                    "summary": "Fix login",
                    "status": {"name": "In Progress"},
                    "priority": {"name": "High"},
                    "issuetype": {"name": "Bug"},
                    "self": "https://jira.example.com/rest/api/2/issue/ENG-1",
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response):
        tasks = client.fetch_open_tasks()

    assert len(tasks) == 1
    assert tasks[0]["key"] == "ENG-1"
    assert tasks[0]["summary"] == "Fix login"


def test_jira_update_task_status_returns_true_on_success():
    client = make_jira_client()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response):
        result = client.update_task_status("ENG-1", "done")

    assert result is True


def test_jira_update_task_status_returns_false_on_error():
    client = make_jira_client()
    with patch("httpx.post", side_effect=httpx.HTTPError("fail")):
        result = client.update_task_status("ENG-1", "done")
    assert result is False


def test_notion_update_daily_page_returns_true_on_success():
    from src.integrations import NotionClient
    client = NotionClient(daily_page_id="page-id", token="tok")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.patch", return_value=mock_response):
        result = client.update_daily_page("session summary text")

    assert result is True


def test_notion_update_page_returns_false_on_error():
    from src.integrations import NotionClient
    client = NotionClient(daily_page_id="page-id", token="tok")
    with patch("httpx.patch", side_effect=httpx.HTTPError("fail")):
        result = client.update_daily_page("summary")
    assert result is False


def test_krisp_fetch_recent_meetings():
    from src.integrations import KrispClient
    client = KrispClient(api_base_url="https://api.krisp.ai", token="tok")
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"id": "m1", "title": "Standup", "transcript": "discussed ENG-1", "url": "https://krisp.ai/m/1"}
    ]
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response):
        meetings = client.fetch_recent_meetings(limit=5)

    assert len(meetings) == 1
    assert meetings[0]["id"] == "m1"
