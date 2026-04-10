from typing import Optional
import httpx


class ConfigurationError(Exception):
    pass


class JiraClient:
    def __init__(self, base_url: str, token: str, project_key: str):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._project_key = project_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def fetch_open_tasks(self) -> list[dict]:
        if not self._token:
            raise ConfigurationError("Jira token not configured")
        jql = f"project={self._project_key} AND statusCategory != Done ORDER BY priority DESC"
        url = f"{self._base_url}/rest/api/2/search"
        response = httpx.get(url, params={"jql": jql, "maxResults": 50}, headers=self._headers())
        response.raise_for_status()
        issues = response.json().get("issues", [])
        return [
            {
                "key": issue["key"],
                "summary": issue["fields"]["summary"],
                "status": issue["fields"]["status"]["name"],
                "priority": issue["fields"]["priority"]["name"],
                "issue_type": issue["fields"]["issuetype"]["name"],
                "url": issue["fields"].get("self", ""),
            }
            for issue in issues
        ]

    def update_task_status(self, source_id: str, status: str) -> bool:
        if not self._token:
            return False
        url = f"{self._base_url}/rest/api/2/issue/{source_id}/transitions"
        try:
            response = httpx.post(url, json={"transition": {"name": status}}, headers=self._headers())
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False


class KrispClient:
    def __init__(self, api_base_url: str, token: str):
        self._base_url = api_base_url.rstrip("/")
        self._token = token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def fetch_recent_meetings(self, limit: int = 10) -> list[dict]:
        if not self._token:
            return []
        url = f"{self._base_url}/meetings"
        try:
            response = httpx.get(url, params={"limit": limit}, headers=self._headers())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return []


class NotionClient:
    def __init__(self, daily_page_id: str, token: str):
        self._daily_page_id = daily_page_id
        self._token = token
        self._base_url = "https://api.notion.com/v1"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def update_daily_page(self, summary: str) -> bool:
        return self.update_page_property(self._daily_page_id, "Session Summary", summary)

    def update_page_property(self, page_id: str, property_name: str, value: str) -> bool:
        if not self._token:
            return False
        url = f"{self._base_url}/pages/{page_id}"
        try:
            response = httpx.patch(
                url,
                json={"properties": {property_name: {"rich_text": [{"text": {"content": value}}]}}},
                headers=self._headers(),
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False
