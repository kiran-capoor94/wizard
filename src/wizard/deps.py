"""Provider functions for FastMCP Depends() injection."""

import logging

from .config import settings
from .repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
)
from .security import SecurityService
from .services import SessionCloser
from .transcript import CaptureSynthesiser, TranscriptReader

logger = logging.getLogger(__name__)


def get_security() -> SecurityService:
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
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
    return SessionCloser(security=get_security())


def get_capture_synthesiser() -> CaptureSynthesiser:
    return CaptureSynthesiser(
        reader=TranscriptReader(),
        note_repo=NoteRepository(),
        security=get_security(),
    )
