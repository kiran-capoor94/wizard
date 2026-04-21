"""Repositories package — re-exports all public symbols for backward compatibility."""

from .meeting import MeetingRepository
from .note import NoteRepository, build_rolling_summary
from .session import SessionRepository, find_latest_session_with_notes
from .task import TaskRepository
from .task_state import TaskStateRepository

__all__ = [
    "MeetingRepository",
    "NoteRepository",
    "SessionRepository",
    "TaskRepository",
    "TaskStateRepository",
    "build_rolling_summary",
    "find_latest_session_with_notes",
]
