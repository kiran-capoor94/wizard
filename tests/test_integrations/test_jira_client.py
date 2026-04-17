"""Tests for JiraClient."""

import httpx
import pytest
import respx


def make_jira_client(base_url="https://jira.example.com", token="tok", project_key="ENG"):
    from wizard.integrations import JiraClient
    return JiraClient(base_url=base_url, token=token, project_key=project_key)


def test_jira_client_is_none_when_no_token():
    client = make_jira_client(token="")
    assert client._client is None


def test_jira_client_is_configured_when_token_provided():
    client = make_jira_client(token="tok")
    assert client._client is not None
    assert isinstance(client._client, httpx.Client)


def test_jira_raises_configuration_error_on_fetch_when_no_token():
    from wizard.integrations import ConfigurationError
    client = make_jira_client(token="")
    with pytest.raises(ConfigurationError):
        client.fetch_open_tasks()


def test_jira_raises_configuration_error_on_update_when_no_token():
    from wizard.integrations import ConfigurationError
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


@respx.mock
def test_jira_fetch_open_tasks_uses_browse_url():
    """fetch_open_tasks should return the browse URL, not the REST API self URL."""
    respx.post("https://jira.example.com/rest/api/3/search/jql").mock(
        return_value=httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "ENG-42",
                        "fields": {
                            "summary": "Some task",
                            "status": {"name": "To Do"},
                            "priority": {"name": "Medium"},
                            "issuetype": {"name": "Story"},
                            "self": "https://jira.example.com/rest/api/3/issue/12345",
                        },
                    }
                ]
            },
        )
    )
    client = make_jira_client()
    tasks = client.fetch_open_tasks()

    assert len(tasks) == 1
    assert tasks[0].url == "https://jira.example.com/browse/ENG-42"


def test_jira_update_task_status_returns_false_on_missing_transition(monkeypatch):
    from wizard.integrations import JiraClient

    client = JiraClient(base_url="https://jira.example.com", token="tok", project_key="ENG", email="a@b.com")
    # Stub _get_transition_id to return None
    monkeypatch.setattr(client, "_get_transition_id", lambda *args: None)
    result = client.update_task_status("ENG-1", "Nonexistent Status")
    assert result is False
