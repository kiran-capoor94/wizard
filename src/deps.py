"""Cached dependency singletons — one instance per process.

Tests call <func>.cache_clear() to reset.
Config changes require restart.
"""

import logging
from functools import lru_cache

from .config import settings
from .integrations import JiraClient, NotionClient
from .repositories import MeetingRepository, NoteRepository, TaskRepository
from .security import SecurityService
from .services import SyncService, WriteBackService

logger = logging.getLogger(__name__)


@lru_cache
def jira_client() -> JiraClient:
    logger.debug("Creating JiraClient singleton")
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token,
        project_key=settings.jira.project_key,
        email=settings.jira.email,
    )


@lru_cache
def notion_client() -> NotionClient:
    logger.debug("Creating NotionClient singleton")
    return NotionClient(
        token=settings.notion.token,
        daily_page_id=settings.notion.daily_page_id,
        tasks_db_id=settings.notion.tasks_db_id,
        meetings_db_id=settings.notion.meetings_db_id,
    )


@lru_cache
def security() -> SecurityService:
    logger.debug("Creating SecurityService singleton")
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
    )


@lru_cache
def sync_service() -> SyncService:
    logger.debug("Creating SyncService singleton")
    return SyncService(jira=jira_client(), notion=notion_client(), security=security())


@lru_cache
def writeback() -> WriteBackService:
    logger.debug("Creating WriteBackService singleton")
    return WriteBackService(jira=jira_client(), notion=notion_client())


@lru_cache
def task_repo() -> TaskRepository:
    logger.debug("Creating TaskRepository singleton")
    return TaskRepository()


@lru_cache
def meeting_repo() -> MeetingRepository:
    logger.debug("Creating MeetingRepository singleton")
    return MeetingRepository()


@lru_cache
def note_repo() -> NoteRepository:
    logger.debug("Creating NoteRepository singleton")
    return NoteRepository()
