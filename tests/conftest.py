"""Shared fixtures for behavioural testing."""

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from tests.fakes import (
    FakeContext,
    FakeJiraClient,
    FakeNotionClient,
    FakeSyncService,
    FakeWriteBackService,
)
from wizard.repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
)
from wizard.security import SecurityService


@pytest.fixture(scope="session")
def db_engine():
    """In-memory SQLite engine with all tables created from models."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Per-test DB session. Rolls back after each test for isolation."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    @contextmanager
    def _test_get_session() -> Generator[Session, None, None]:
        yield session

    with patch("wizard.tools.session_tools.get_session", _test_get_session), \
         patch("wizard.tools.task_tools.get_session", _test_get_session), \
         patch("wizard.tools.meeting_tools.get_session", _test_get_session):
        yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def fake_ctx():
    return FakeContext()


@pytest.fixture
def fake_jira():
    return FakeJiraClient()


@pytest.fixture
def fake_notion():
    return FakeNotionClient()


@pytest.fixture
def fake_sync():
    return FakeSyncService()


@pytest.fixture
def fake_writeback():
    return FakeWriteBackService()


@pytest.fixture
def security():
    """Real SecurityService -- scrubbing is pure regex, no I/O."""
    return SecurityService(allowlist=[r"ENG-\d+"], enabled=True)


@pytest.fixture
def task_repo():
    return TaskRepository()


@pytest.fixture
def note_repo():
    return NoteRepository()


@pytest.fixture
def meeting_repo():
    return MeetingRepository()


@pytest.fixture
def task_state_repo():
    return TaskStateRepository()
