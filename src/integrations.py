import base64
import logging
import re

import httpx
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError
from notion_client.helpers import collect_paginated_api

from .schemas import (
    JiraTaskData,
    NotionMeetingData,
    NotionTaskData,
    NotionTitle,
    NotionRichText,
    NotionSelect,
    NotionMultiSelect,
    NotionUrl,
    NotionDate,
    NotionStatus,
)

HTTPX_TIMEOUT = httpx.Timeout(10.0)

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    pass


class JiraClient:
    def __init__(self, base_url: str, token: str, project_key: str, email: str = ""):
        self._base_url = base_url.rstrip("/")
        self._project_key = project_key
        self._email = email
        self._token = token
        self._client: httpx.Client | None = None
        if token:
            self._client = httpx.Client(
                base_url=f"{self._base_url}/rest/api/3",
                headers={
                    "Authorization": f"Basic {base64.b64encode(f'{email}:{token}'.encode()).decode()}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=HTTPX_TIMEOUT,
            )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _require_client(self) -> httpx.Client:
        if self._client is None:
            raise ConfigurationError("Jira token not configured")
        return self._client

    def fetch_open_tasks(self) -> list[JiraTaskData]:
        client = self._require_client()
        try:
            jql = f"project={self._project_key} AND statusCategory != Done ORDER BY priority DESC"
            response = client.post(
                "/search/jql",
                json={"jql": jql, "maxResults": 50},
            )
            response.raise_for_status()
            issues = response.json().get("issues", [])
            if not issues:
                logger.warning(
                    "Jira fetch_open_tasks: got 0 issues - may lack Browse Projects permission"
                )
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
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Jira fetch_open_tasks HTTP error: %s - Response: %s",
                e,
                e.response.text[:500],
            )
            return []
        except httpx.HTTPError as e:
            logger.warning("Jira fetch_open_tasks failed: %s", e)
            return []
        except httpx.HTTPError as e:
            logger.warning("Jira fetch_open_tasks failed: %s", e)
            return []

    def update_task_status(self, source_id: str, status: str) -> bool:
        client = self._require_client()
        try:
            response = client.post(
                f"/issue/{source_id}/transitions",
                json={"transition": {"id": self._get_transition_id(source_id, status)}},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.warning("Jira update_task_status failed: %s", e)
            return False

    def _get_transition_id(self, issue_key: str, status: str) -> str | None:
        """Get transition ID for a given status name."""
        client = self._require_client()
        try:
            response = client.get(f"/issue/{issue_key}/transitions")
            response.raise_for_status()
            transitions = response.json().get("transitions", [])
            for t in transitions:
                if t.get("name", "").lower() == status.lower():
                    return t.get("id")
        except httpx.HTTPError:
            pass
        return None


def _extract_jira_key(url: str | None) -> str | None:
    """Extract Jira issue key from URL like https://org.atlassian.net/browse/ENG-123"""
    if not url:
        return None
    match = re.search(r"/browse/([A-Z]+-\d+)", url)
    return match.group(1) if match else None


def _extract_krisp_id(url: str | None) -> str | None:
    """Extract meeting ID from last path segment of a Krisp URL."""
    if not url:
        return None
    try:
        segment = url.rstrip("/").split("/")[-1].split("?")[0].strip()
        return segment or None
    except Exception:
        logger.warning("Failed to extract krisp_id from URL: %s", url)
        return None


# ============================================================================
# NotionClient
# ============================================================================


class NotionClient:
    def __init__(
        self, token: str, daily_page_id: str, tasks_db_id: str, meetings_db_id: str
    ):
        self._daily_page_id = daily_page_id
        self._tasks_db_id = tasks_db_id
        self._meetings_db_id = meetings_db_id
        self._client = NotionSdkClient(auth=token) if token else None

    def _require_client(self) -> NotionSdkClient:
        if self._client is None:
            raise ConfigurationError("Notion token not configured")
        return self._client

    def _query_database(self, database_id: str, **kwargs) -> dict:
        """Query a database by ID using data_sources API (v3.0)."""
        client = self._require_client()
        return client.data_sources.query(data_source_id=database_id, **kwargs)

    def fetch_tasks(self) -> list[NotionTaskData]:
        """Query Tasks DB, return normalised NotionTaskData models."""
        self._require_client()

        try:
            pages = collect_paginated_api(
                self._query_database, database_id=self._tasks_db_id
            )
            tasks = []
            for page in pages:
                page_id = page.get("id")
                props = page.get("properties", {})

                jira_url = NotionUrl.model_validate(props.get("Jira", {})).url
                task = NotionTaskData(
                    notion_id=page_id,
                    name=NotionTitle.model_validate(props.get("Task", {})).text,
                    status=NotionStatus.model_validate(props.get("Status", {})).name,
                    priority=NotionSelect.model_validate(
                        props.get("Priority", {})
                    ).name,
                    due_date=NotionDate.model_validate(props.get("Due date", {})).start,
                    jira_url=jira_url,
                    jira_key=_extract_jira_key(jira_url),
                )
                tasks.append(task)
            return tasks
        except Exception as e:
            logger.warning("Notion fetch_tasks failed: %s - %s", type(e).__name__, e)
            return []

    def fetch_meetings(self) -> list[NotionMeetingData]:
        """Query Meeting Notes DB, return normalised NotionMeetingData models."""
        self._require_client()

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
                    title=NotionTitle.model_validate(
                        props.get("Meeting name", {})
                    ).text,
                    categories=NotionMultiSelect.model_validate(
                        props.get("Category", {})
                    ).names,
                    summary=NotionRichText.model_validate(
                        props.get("Summary", {})
                    ).text,
                    krisp_url=NotionUrl.model_validate(props.get("Krisp URL", {})).url,
                    date=NotionDate.model_validate(props.get("Date", {})).start,
                )
                meetings.append(meeting)
            return meetings
        except Exception as e:
            logger.warning("Notion fetch_meetings failed: %s - %s", type(e).__name__, e)
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
        client = self._require_client()

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

            response = client.pages.create(
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
        client = self._require_client()

        try:
            properties = {
                "Meeting name": {"title": [{"text": {"content": title}}]},
                "Category": {"multi_select": [{"name": category}]},
            }

            if krisp_url:
                properties["Krisp URL"] = {"url": krisp_url}
            if summary:
                properties["Summary"] = {"rich_text": [{"text": {"content": summary}}]}

            response = client.pages.create(
                parent={"database_id": self._meetings_db_id},
                properties=properties,
            )
            return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]
        except APIResponseError as e:
            logger.warning("Notion create_meeting_page failed: %s", e)
            return None

    def update_task_status(self, page_id: str, status: str) -> bool:
        """Update Status property on task page."""
        client = self._require_client()

        try:
            client.pages.update(
                page_id=page_id,
                properties={"Status": {"status": {"name": status}}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_task_status failed: %s", e)
            return False

    def update_meeting_summary(self, page_id: str, summary: str) -> bool:
        """Update Summary property on meeting page."""
        client = self._require_client()

        try:
            client.pages.update(
                page_id=page_id,
                properties={"Summary": {"rich_text": [{"text": {"content": summary}}]}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_meeting_summary failed: %s", e)
            return False

    def update_daily_page(self, summary: str) -> bool:
        """Update Session Summary property on daily page."""
        client = self._require_client()

        try:
            client.pages.update(
                page_id=self._daily_page_id,
                properties={
                    "Session Summary": {"rich_text": [{"text": {"content": summary}}]}
                },
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_daily_page failed: %s", e)
            return False
