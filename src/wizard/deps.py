"""Provider functions for FastMCP Depends() injection.

Each function constructs and returns a fresh instance.
FastMCP caches results per-request when used via Depends().
CLI commands call these directly as plain callables.
"""

import logging

from .config import settings
from .integrations import JiraClient, NotionClient
from .repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
)
from .security import SecurityService
from .services import SessionCloser, SyncService, WriteBackService

logger = logging.getLogger(__name__)


def get_jira_client() -> JiraClient:
    logger.debug("Creating JiraClient")
    return JiraClient(
        base_url=settings.jira.base_url,
        token=settings.jira.token.get_secret_value(),
        project_key=settings.jira.project_key,
        email=settings.jira.email,
    )


def get_notion_client() -> NotionClient:
    logger.debug("Creating NotionClient")
    return NotionClient(
        token=settings.notion.token.get_secret_value(),
        daily_page_parent_id=settings.notion.daily_page_parent_id,
        tasks_ds_id=settings.notion.tasks_ds_id,
        meetings_ds_id=settings.notion.meetings_ds_id,
        schema=settings.notion.notion_schema,
    )


def get_security() -> SecurityService:
    logger.debug("Creating SecurityService")
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
    )


def get_sync_service() -> SyncService:
    logger.debug("Creating SyncService")
    return SyncService(
        jira=get_jira_client(),
        notion=get_notion_client(),
        security=get_security(),
    )


def get_writeback() -> WriteBackService:
    logger.debug("Creating WriteBackService")
    return WriteBackService(
        jira=get_jira_client(),
        notion=get_notion_client(),
        security=get_security(),
    )


def get_task_repo() -> TaskRepository:
    return TaskRepository()


def get_meeting_repo() -> MeetingRepository:
    return MeetingRepository()


def get_note_repo() -> NoteRepository:
    return NoteRepository()


def get_task_state_repo() -> TaskStateRepository:
    return TaskStateRepository()


def get_session_closer() -> SessionCloser:
    return SessionCloser()
