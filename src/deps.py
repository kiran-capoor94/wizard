"""Cached dependency singletons — one instance per process.

Tests call <func>.cache_clear() to reset.
Config changes require restart.
"""

from functools import lru_cache

from .config import settings
from .integrations import JiraClient, NotionClient
from .repositories import MeetingRepository, NoteRepository, TaskRepository
from .security import SecurityService
from .services import SyncService, WriteBackService


@lru_cache
def jira_client() -> JiraClient:
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
    )


@lru_cache
def notion_client() -> NotionClient:
    return NotionClient(
        token=settings.notion.token,
        daily_page_id=settings.notion.daily_page_id,
        tasks_db_id=settings.notion.tasks_db_id,
        meetings_db_id=settings.notion.meetings_db_id,
    )


@lru_cache
def security() -> SecurityService:
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
    )


@lru_cache
def sync_service() -> SyncService:
    return SyncService(jira=jira_client(), notion=notion_client(), security=security())


@lru_cache
def writeback() -> WriteBackService:
    return WriteBackService(jira=jira_client(), notion=notion_client())


@lru_cache
def task_repo() -> TaskRepository:
    return TaskRepository()


@lru_cache
def meeting_repo() -> MeetingRepository:
    return MeetingRepository()


@lru_cache
def note_repo() -> NoteRepository:
    return NoteRepository()
