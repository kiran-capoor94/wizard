"""Provider functions for FastMCP Depends() injection."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session

from .config import WizardPaths, settings
from .database import get_session as _get_db_session_impl
from .repositories import (
    MeetingRepository,
    NoteRepository,
    SessionRepository,
    TaskRepository,
    TaskStateRepository,
)
from .security import PseudonymStore, SecurityService
from .services import SessionCloser

logger = logging.getLogger(__name__)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provide a DB session for Depends() injection.

    Centralised here so tests can patch a single target
    (``wizard.deps.get_db_session``) instead of every per-module binding.
    """
    with _get_db_session_impl() as db:
        yield db


def get_security() -> SecurityService:
    return SecurityService(
        allowlist=settings.scrubbing.allowlist,
        enabled=settings.scrubbing.enabled,
        store=PseudonymStore(),
    )


def get_task_repo() -> TaskRepository:
    return TaskRepository()


def get_meeting_repo() -> MeetingRepository:
    return MeetingRepository()


def get_note_repo() -> NoteRepository:
    return NoteRepository()


def get_task_state_repo() -> TaskStateRepository:
    return TaskStateRepository()


def get_session_repo() -> SessionRepository:
    return SessionRepository()


def get_session_closer() -> SessionCloser:
    return SessionCloser(security=get_security(), settings=settings)


def get_wizard_paths() -> WizardPaths:
    return settings.paths


def get_skill_roots() -> list[Path]:
    """Return the default skill search roots for mode tools."""
    return [settings.paths.installed_skills, settings.paths.package_skills]
