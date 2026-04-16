import base64
import datetime
import logging
import re

import httpx
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError
from notion_client.helpers import collect_paginated_api

from .config import NotionSchemaSettings
from .schemas import (
    DailyPageResult,
    JiraTaskData,
    NotionDate,
    NotionMeetingData,
    NotionMultiSelect,
    NotionRichText,
    NotionSelect,
    NotionStatus,
    NotionTaskData,
    NotionTitle,
    NotionUrl,
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
                    url=f"{self._base_url}/browse/{issue['key']}",
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


def _today_title() -> str:
    """Build today's daily page title, e.g. 'Friday 11 April 2026'."""
    today = datetime.date.today()
    return f"{today:%A} {today.day} {today:%B %Y}"


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


def _is_daily_page_title(title: str) -> bool:
    """Return True if title matches the daily-page format, e.g. 'Wednesday 9 April 2026'."""
    try:
        datetime.datetime.strptime(title, "%A %d %B %Y")
        return True
    except ValueError:
        return False


class NotionClient:
    def __init__(
        self,
        token: str,
        daily_page_parent_id: str,
        tasks_ds_id: str,
        meetings_ds_id: str,
        schema: NotionSchemaSettings | None = None,
    ):
        self._daily_page_parent_id = daily_page_parent_id
        self._tasks_ds_id = tasks_ds_id
        self._meetings_ds_id = meetings_ds_id
        self._client = NotionSdkClient(auth=token) if token else None
        self._schema = schema if schema is not None else NotionSchemaSettings()

    def _require_client(self) -> NotionSdkClient:
        if self._client is None:
            raise ConfigurationError("Notion token not configured")
        return self._client

    def _query_database(self, data_source_id: str, **kwargs) -> dict:
        """Query a data source using data_sources API (v3.0)."""
        client = self._require_client()
        return client.data_sources.query(data_source_id=data_source_id, **kwargs)  # pyright: ignore[reportReturnType]

    def _list_daily_page_parent_children(self) -> list[dict]:
        """Return non-archived child_page blocks under the daily page parent."""
        client = self._require_client()
        blocks = collect_paginated_api(
            client.blocks.children.list,
            block_id=self._daily_page_parent_id,
        )
        return [
            block
            for block in blocks
            if block.get("type") == "child_page" and not block.get("archived", False)
        ]

    def find_daily_page(self, title: str) -> str | None:
        """Find a child page of the daily page parent matching the given title."""
        try:
            for block in self._list_daily_page_parent_children():
                if block.get("child_page", {}).get("title") == title:
                    return block["id"]
            return None
        except Exception as e:
            logger.warning("Notion find_daily_page failed: %s", e)
            return None

    def create_daily_page(self, title: str) -> str | None:
        """Create a child page under the daily page parent."""
        client = self._require_client()
        try:
            response = client.pages.create(
                parent={"page_id": self._daily_page_parent_id},
                properties={
                    "title": [{"text": {"content": title}}],
                    self._schema.daily_page_session_summary: {"rich_text": [{"text": {"content": ""}}]},
                },
            )
            return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]
        except APIResponseError as e:
            logger.warning("Notion create_daily_page failed: %s", e)
            return None

    def archive_page(self, page_id: str) -> bool:
        """Archive a Notion page by ID."""
        client = self._require_client()
        try:
            client.pages.update(page_id=page_id, archived=True)
            return True
        except APIResponseError as e:
            logger.warning("Notion archive_page failed: %s", e)
            return False

    def ensure_daily_page(self) -> DailyPageResult:
        """Find or create today's daily page. Archive stale daily pages."""

        title = _today_title()
        children = self._list_daily_page_parent_children()

        page_id: str | None = None
        stale_ids: list[str] = []
        for block in children:
            block_title = block.get("child_page", {}).get("title", "")
            if block_title == title:
                page_id = block["id"]
            elif _is_daily_page_title(block_title):
                stale_ids.append(block["id"])
            # Non-daily pages are left untouched

        created = False
        if page_id is None:
            page_id = self.create_daily_page(title)
            if page_id is None:
                raise ConfigurationError(
                    f"Failed to create daily page '{title}' under daily page parent"
                )
            created = True

        archived_count = 0
        for stale_id in stale_ids:
            if self.archive_page(stale_id):
                archived_count += 1

        return DailyPageResult(
            page_id=page_id, created=created, archived_count=archived_count
        )

    def fetch_tasks(self) -> list[NotionTaskData]:
        """Query Tasks DB, return normalised NotionTaskData models."""
        self._require_client()

        try:
            pages = collect_paginated_api(
                self._query_database, data_source_id=self._tasks_ds_id
            )
            tasks = []
            for page in pages:
                page_id = page.get("id")
                props = page.get("properties", {})

                jira_url = NotionUrl.model_validate(
                    props.get(self._schema.task_jira_key, {})
                ).url
                task = NotionTaskData(
                    notion_id=page_id,
                    name=NotionTitle.model_validate(
                        props.get(self._schema.task_name, {})
                    ).text,
                    status=NotionStatus.model_validate(
                        props.get(self._schema.task_status, {})
                    ).name,
                    priority=NotionSelect.model_validate(
                        props.get(self._schema.task_priority, {})
                    ).name,
                    due_date=NotionDate.model_validate(
                        props.get(self._schema.task_due_date, {})
                    ).start,
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
                self._query_database, data_source_id=self._meetings_ds_id
            )
            meetings = []
            for page in pages:
                page_id = page.get("id")
                props = page.get("properties", {})

                meeting = NotionMeetingData(
                    notion_id=page_id,
                    title=NotionTitle.model_validate(
                        props.get(self._schema.meeting_title, {})
                    ).text,
                    categories=NotionMultiSelect.model_validate(
                        props.get(self._schema.meeting_category, {})
                    ).names,
                    summary=NotionRichText.model_validate(
                        props.get(self._schema.meeting_summary, {})
                    ).text,
                    krisp_url=NotionUrl.model_validate(
                        props.get(self._schema.meeting_url, {})
                    ).url,
                    date=NotionDate.model_validate(
                        props.get(self._schema.meeting_date, {})
                    ).start,
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

        properties: dict = {
            self._schema.task_name: {"title": [{"text": {"content": name}}]},
            self._schema.task_status: {"status": {"name": status}},
        }

        if priority:
            properties[self._schema.task_priority] = {"select": {"name": priority}}
        if jira_url:
            properties[self._schema.task_jira_key] = {"url": jira_url}
        if due_date:
            properties[self._schema.task_due_date] = {"date": {"start": due_date}}

        response = client.pages.create(
            parent={"data_source_id": self._tasks_ds_id},
            properties=properties,
        )
        return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]

    def create_meeting_page(
        self,
        title: str,
        category: str,
        krisp_url: str | None = None,
        summary: str | None = None,
    ) -> str | None:
        """Create page in Meeting Notes DB, return page_id."""
        client = self._require_client()

        properties: dict = {
            self._schema.meeting_title: {"title": [{"text": {"content": title}}]},
            self._schema.meeting_category: {"multi_select": [{"name": category}]},
        }

        if krisp_url:
            properties[self._schema.meeting_url] = {"url": krisp_url}
        if summary:
            properties[self._schema.meeting_summary] = {
                "rich_text": [{"text": {"content": summary}}]
            }

        response = client.pages.create(
            parent={"data_source_id": self._meetings_ds_id},
            properties=properties,
        )
        return response.get("id")  # pyright: ignore[reportAttributeAccessIssue]

    def update_task_status(self, page_id: str, status: str) -> bool:
        """Update Status property on task page."""
        client = self._require_client()

        try:
            client.pages.update(
                page_id=page_id,
                properties={self._schema.task_status: {"status": {"name": status}}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_task_status failed: %s", e)
            return False

    def update_task_due_date(self, page_id: str, due_date: str) -> bool:
        """Update due_date property on task page. due_date in ISO format."""
        client = self._require_client()
        try:
            client.pages.update(
                page_id=page_id,
                properties={self._schema.task_due_date: {"date": {"start": due_date}}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_task_due_date failed: %s", e)
            return False

    def update_task_priority(self, page_id: str, priority: str) -> bool:
        """Update priority select property on task page."""
        client = self._require_client()
        try:
            client.pages.update(
                page_id=page_id,
                properties={self._schema.task_priority: {"select": {"name": priority}}},
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_task_priority failed: %s", e)
            return False

    def update_meeting_summary(self, page_id: str, summary: str) -> bool:
        """Update Summary property on meeting page."""
        client = self._require_client()

        try:
            client.pages.update(
                page_id=page_id,
                properties={
                    self._schema.meeting_summary: {
                        "rich_text": [{"text": {"content": summary}}]
                    }
                },
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_meeting_summary failed: %s", e)
            return False

    def append_paragraph_to_page(self, page_id: str, text: str) -> bool:
        """Append a paragraph block to an existing Notion page."""
        client = self._require_client()
        try:
            client.blocks.children.append(
                block_id=page_id,
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": text}}]
                        },
                    }
                ],
            )
            return True
        except Exception as e:
            logger.warning("Notion append_paragraph_to_page failed: %s", e)
            return False

    def update_daily_page(self, page_id: str, summary: str) -> bool:
        """Update Session Summary property on a daily page."""
        client = self._require_client()
        try:
            client.pages.update(
                page_id=page_id,
                properties={
                    self._schema.daily_page_session_summary: {"rich_text": [{"text": {"content": summary}}]}
                },
            )
            return True
        except APIResponseError as e:
            logger.warning("Notion update_daily_page failed: %s", e)
            return False
