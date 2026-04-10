import logging
import re

import httpx
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError
from notion_client.helpers import collect_paginated_api

from .schemas import JiraTaskData, NotionMeetingData, NotionTaskData

HTTPX_TIMEOUT = httpx.Timeout(10.0)

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    pass


class JiraClient:
    def __init__(self, base_url: str, token: str, project_key: str):
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._client: httpx.Client | None = (
            httpx.Client(
                base_url=f"{self._base_url}/rest/api/2",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=HTTPX_TIMEOUT,
            )
            if token
            else None
        )

    def fetch_open_tasks(self) -> list[JiraTaskData]:
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        try:
            jql = f"project={self._project_key} AND statusCategory != Done ORDER BY priority DESC"
            response = self._client.get(
                "/search", params={"jql": jql, "maxResults": 50}
            )
            response.raise_for_status()
            issues = response.json().get("issues", [])
            return [
                JiraTaskData(
                    key=issue["key"],
                    summary=issue["fields"]["summary"],
                    status=issue["fields"]["status"]["name"],
                    priority=issue["fields"]["priority"]["name"],
                    issue_type=issue["fields"]["issuetype"]["name"],
                    url=issue["fields"].get("self", ""),
                )
                for issue in issues
            ]
        except httpx.HTTPError as e:
            logger.warning("Jira fetch_open_tasks failed: %s", e)
            return []

    def update_task_status(self, source_id: str, status: str) -> bool:
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        try:
            response = self._client.post(
                f"/issue/{source_id}/transitions",
                json={"transition": {"name": status}},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.warning("Jira update_task_status failed: %s", e)
            return False


# ============================================================================
# Helper functions for extracting Notion properties
# ============================================================================


def _extract_jira_key(url: str | None) -> str | None:
    """Extract Jira issue key from URL like https://org.atlassian.net/browse/ENG-123"""
    if not url:
        return None
    match = re.search(r"/browse/([A-Z]+-\d+)", url)
    return match.group(1) if match else None


def _get_title(properties: dict, key: str) -> str | None:
    """Extract plain text from Notion title property."""
    prop = properties.get(key, {})
    if prop and "title" in prop:
        titles = prop["title"]
        if titles and len(titles) > 0:
            return titles[0].get("plain_text")
    return None


def _get_rich_text(properties: dict, key: str) -> str | None:
    """Extract plain text from Notion rich_text property."""
    prop = properties.get(key, {})
    if prop and "rich_text" in prop:
        texts = prop["rich_text"]
        if texts and len(texts) > 0:
            return texts[0].get("plain_text")
    return None


def _get_select(properties: dict, key: str) -> str | None:
    """Extract name from Notion select property."""
    prop = properties.get(key, {})
    if prop and "select" in prop and prop["select"]:
        return prop["select"].get("name")
    return None


def _get_multi_select(properties: dict, key: str) -> list[str] | None:
    """Extract list of names from Notion multi_select property."""
    prop = properties.get(key, {})
    if prop and "multi_select" in prop:
        items = prop["multi_select"]
        if isinstance(items, list):
            return [item.get("name") for item in items if item and "name" in item]
    return None


def _get_url(properties: dict, key: str) -> str | None:
    """Extract URL from Notion url property."""
    prop = properties.get(key, {})
    if prop and "url" in prop:
        return prop["url"]
    return None


def _get_date_start(properties: dict, key: str) -> str | None:
    """Extract start date from Notion date property."""
    prop = properties.get(key, {})
    if prop and "date" in prop and prop["date"]:
        return prop["date"].get("start")
    return None


def _get_status(properties: dict, key: str) -> str | None:
    """Extract name from Notion status property."""
    prop = properties.get(key, {})
    if prop and "status" in prop and prop["status"]:
        return prop["status"].get("name")
    return None


# ============================================================================
# NotionClient
# ============================================================================


class NotionClient:
    def __init__(
        self, token: str, daily_page_id: str, tasks_db_id: str, meetings_db_id: str
    ):
        self._token = token
        self._daily_page_id = daily_page_id
        self._tasks_db_id = tasks_db_id
        self._meetings_db_id = meetings_db_id
        self._client = NotionSdkClient(auth=token) if token else None

    def _query_database(self, database_id: str, **kwargs) -> dict:
        """Query a database by ID. Wraps client.request for v3.0 compat (databases.query was removed)."""
        if self._client is None:
            raise ConfigurationError("Notion token not configured")
        return self._client.request(
            path=f"databases/{database_id}/query",
            method="POST",
            body=kwargs,
        )

    def fetch_tasks(self) -> list[NotionTaskData]:
        """Query Tasks DB, return normalised NotionTaskData models."""
        if not self._token:
            raise ConfigurationError("Notion token not configured")

        try:
            pages = collect_paginated_api(
                self._query_database, database_id=self._tasks_db_id
            )
            tasks = []
            for page in pages:
                page_id = page.get("id")
                props = page.get("properties", {})

                task = NotionTaskData(
                    notion_id=page_id,
                    name=_get_title(props, "Task"),
                    status=_get_status(props, "Status"),
                    priority=_get_select(props, "Priority"),
                    due_date=_get_date_start(props, "Due date"),
                    jira_url=_get_url(props, "Jira"),
                    jira_key=_extract_jira_key(_get_url(props, "Jira")),
                )
                tasks.append(task)
            return tasks
        except APIResponseError as e:
            logger.warning("Notion fetch_tasks failed: %s", e)
            return []

    def fetch_meetings(self) -> list[NotionMeetingData]:
        """Query Meeting Notes DB, return normalised NotionMeetingData models."""
        if not self._token:
            raise ConfigurationError("Notion token not configured")

        try:
            pages = collect_paginated_api(
                self._query_database, database_id=self._meetings_db_id
            )
            meetings = []
            for page in pages:
                page_id = page.get("id")
                props = page.get("properties", {})

                meeting = NotionMeetingData(
                    notion_id=page_id,
                    title=_get_title(props, "Meeting name"),
                    categories=_get_multi_select(props, "Category") or [],
                    summary=_get_rich_text(props, "Summary"),
                    krisp_url=_get_url(props, "Krisp URL"),
                    date=_get_date_start(props, "Date"),
                )
                meetings.append(meeting)
            return meetings
        except APIResponseError as e:
            logger.warning("Notion fetch_meetings failed: %s", e)
            return []

    def create_task_page(
        self,
        name: str,
        status: str,
        priority: str | None = None,
        jira_url: str | None = None,
        due_date: str | None = None,
    ) -> str | None:
        """Create page in Tasks DB, return page_id."""
        if self._client is None:
            raise ConfigurationError("Notion token not configured")

        try:
            properties: dict = {
                "Task": {"title": [{"text": {"content": name}}]},
                "Status": {"status": {"name": status}},
            }

            if priority:
                properties["Priority"] = {"select": {"name": priority}}
            if jira_url:
                properties["Jira"] = {"url": jira_url}
            if due_date:
                properties["Due date"] = {"date": {"start": due_date}}

            response = self._client.pages.create(
                parent={"database_id": self._tasks_db_id},
                properties=properties,
            )
            return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]
        except APIResponseError as e:
            logger.warning("Notion create_task_page failed: %s", e)
            return None

    def create_meeting_page(
        self,
        title: str,
        category: str,
        krisp_url: str | None = None,
        summary: str | None = None,
    ) -> str | None:
        """Create page in Meeting Notes DB, return page_id."""
        if self._client is None:
            raise ConfigurationError("Notion token not configured")

        try:
            properties = {
                "Meeting name": {"title": [{"text": {"content": title}}]},
                "Category": {"multi_select": [{"name": category}]},
            }

            if krisp_url:
                properties["Krisp URL"] = {"url": krisp_url}
            if summary:
                properties["Summary"] = {"rich_text": [{"text": {"content": summary}}]}

            response = self._client.pages.create(
                parent={"database_id": self._meetings_db_id},
                properties=properties,
            )
            return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]
        except APIResponseError as e:
            logger.warning("Notion create_meeting_page failed: %s", e)
            return None

    def update_task_status(self, page_id: str, status: str) -> bool:
        """Update Status property on task page."""
        if self._client is None:
            raise ConfigurationError("Notion token not configured")

        try:
            self._client.pages.update(
                page_id=page_id,
                properties={"Status": {"status": {"name": status}}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_task_status failed: %s", e)
            return False

    def update_meeting_summary(self, page_id: str, summary: str) -> bool:
        """Update Summary property on meeting page."""
        if self._client is None:
            raise ConfigurationError("Notion token not configured")

        try:
            self._client.pages.update(
                page_id=page_id,
                properties={"Summary": {"rich_text": [{"text": {"content": summary}}]}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_meeting_summary failed: %s", e)
            return False

    def update_daily_page(self, summary: str) -> bool:
        """Update Session Summary property on daily page."""
        if self._client is None:
            raise ConfigurationError("Notion token not configured")

        try:
            self._client.pages.update(
                page_id=self._daily_page_id,
                properties={
                    "Session Summary": {"rich_text": [{"text": {"content": summary}}]}
                },
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_daily_page failed: %s", e)
            return False
