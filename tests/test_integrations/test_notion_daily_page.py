"""Tests for NotionClient daily page operations."""

from unittest.mock import MagicMock, patch

import httpx
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


def _make_child_page_block(block_id: str, title: str, archived: bool = False) -> dict:
    return {
        "id": block_id,
        "type": "child_page",
        "child_page": {"title": title},
        "archived": archived,
    }


def test_notion_find_daily_page_returns_id_when_found():
    """find_daily_page returns the page_id of the matching child page."""
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.pages.create.side_effect = error

        client = make_notion_client()
        result = client.create_daily_page("Friday 11 April 2026")

    assert result is None


def test_notion_archive_page_returns_true_on_success():
    """archive_page calls pages.update with archived=True and returns True."""
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
        mock_instance = MagicMock()
        mock_notion_class.return_value = mock_instance
        mock_instance.pages.update.side_effect = error

        client = make_notion_client()
        result = client.archive_page("some-page-id")

    assert result is False


def test_notion_ensure_daily_page_finds_existing():
    """ensure_daily_page returns existing page without creating, archived_count=0."""
    with patch("wizard.integrations._today_title", return_value="Friday 11 April 2026"):
        with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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
    with patch("wizard.integrations._today_title", return_value="Friday 11 April 2026"):
        with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
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


def test_notion_ensure_daily_page_leaves_non_daily_pages_alone():
    """Permanent (non-daily) pages under daily page parent must not be archived."""
    with patch("wizard.integrations._today_title", return_value="Friday 11 April 2026"):
        with patch("wizard.integrations.NotionSdkClient") as mock_notion_class:
            mock_instance = MagicMock()
            mock_notion_class.return_value = mock_instance
            mock_instance.blocks.children.list.return_value = {
                "results": [
                    _make_child_page_block("stale-daily-id", "Thursday 10 April 2026"),
                    _make_child_page_block("permanent-id", "SISU IQ Design"),
                    _make_child_page_block("another-perm-id", "Architecture Notes"),
                ]
            }
            mock_instance.pages.create.return_value = {"id": "new-daily-id"}
            mock_instance.pages.update.return_value = {}

            client = make_notion_client()
            result = client.ensure_daily_page()

    # Only the old daily page is archived — permanent pages left alone
    assert result.archived_count == 1
    archived_ids = [
        call.kwargs["page_id"]
        for call in mock_instance.pages.update.call_args_list
        if call.kwargs.get("archived") is True
    ]
    assert "stale-daily-id" in archived_ids
    assert "permanent-id" not in archived_ids
    assert "another-perm-id" not in archived_ids
