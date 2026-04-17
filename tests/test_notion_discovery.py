def test_fetch_db_properties_returns_name_type_dict():
    from unittest.mock import MagicMock

    from wizard.notion_discovery import fetch_db_properties

    mock_client = MagicMock()
    mock_client.data_sources.retrieve.return_value = {
        "properties": {
            "Task": {"type": "title"},
            "Status": {"type": "status"},
            "Due date": {"type": "date"},
        }
    }
    result = fetch_db_properties(mock_client, "ds-123")
    assert result == {"Task": "title", "Status": "status", "Due date": "date"}


def test_fetch_db_properties_returns_empty_on_error():
    from unittest.mock import MagicMock

    from wizard.notion_discovery import fetch_db_properties

    mock_client = MagicMock()
    mock_client.data_sources.retrieve.side_effect = Exception("API error")
    result = fetch_db_properties(mock_client, "ds-123")
    assert result == {}


def test_match_properties_exact_name():
    from wizard.notion_discovery import match_properties

    available = {"Task": "title", "Status": "status", "Due date": "date"}
    result = match_properties(available, ["task_name", "task_status", "task_due_date"])
    assert result["task_name"] == "Task"
    assert result["task_status"] == "Status"
    assert result["task_due_date"] == "Due date"


def test_match_properties_case_insensitive_exact():
    from wizard.notion_discovery import match_properties

    available = {"task": "title", "status": "status"}
    result = match_properties(available, ["task_name", "task_status"])
    assert result["task_name"] == "task"
    assert result["task_status"] == "status"


def test_match_properties_type_match_title_to_task_name():
    from wizard.notion_discovery import match_properties

    available = {"My Tasks": "title", "Workflow": "select"}
    result = match_properties(available, ["task_name"])
    assert result["task_name"] == "My Tasks"


def test_match_properties_synonym_match_state_to_task_status():
    from wizard.notion_discovery import match_properties

    available = {"State": "select", "Name": "title"}
    result = match_properties(available, ["task_status"])
    assert result["task_status"] == "State"


def test_match_properties_synonym_match_recording_to_meeting_url():
    from wizard.notion_discovery import match_properties

    available = {"Recording": "url", "Title": "title"}
    result = match_properties(available, ["meeting_url"])
    assert result["meeting_url"] == "Recording"


def test_match_properties_unresolved_returns_none():
    from wizard.notion_discovery import match_properties

    available = {"Foo": "rich_text"}
    result = match_properties(available, ["task_name"])
    assert result["task_name"] is None


def test_match_properties_empty_db():
    from wizard.notion_discovery import match_properties

    result = match_properties({}, ["task_name", "task_status"])
    assert result["task_name"] is None
    assert result["task_status"] is None
