"""Shared fixtures for behavioural testing."""

import os
from pathlib import Path

# Must run before any `wizard.*` import below (including transitively, e.g.
# `wizard.repositories` -> `wizard.database` -> `wizard.config`) — Settings()
# reads WIZARD_CONFIG_FILE once at import time, and wizard.database.engine is
# a module-level singleton built from settings.db right then. Without this,
# a handful of scenario tests call get_session() directly (bypassing the
# per-test mcp_client patching below) and land on the real
# ~/.wizard/wizard.db, writing throwaway session/tool-call rows into
# whatever personal database happens to be configured on the machine
# running the suite.
os.environ.setdefault(
    "WIZARD_CONFIG_FILE", str(Path(__file__).parent / "test_config.json")
)

from collections.abc import AsyncGenerator, Generator  # noqa: E402
from contextlib import ExitStack, contextmanager  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from fastmcp.client import Client  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from wizard.database import create_fts_schema  # noqa: E402
from wizard.database import run_migrations as _run_migrations  # noqa: E402
from wizard.repositories import (  # noqa: E402
    MeetingRepository,
    NoteRepository,
    SessionRepository,
    TaskRepository,
    TaskStateRepository,
)
from wizard.security import SecurityService  # noqa: E402

# The handful of tests that call get_session() directly share this one
# process-wide in-memory engine (same as they always implicitly shared
# whatever `wizard.database.engine` pointed to) — run the real migration
# chain once so it has the full schema, including the FTS5 virtual tables
# that plain SQLModel.metadata.create_all() doesn't know how to create.
_run_migrations()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Fresh in-memory SQLite engine per test — guarantees isolation.

    SQLModel.metadata.create_all() only knows about ORM-mapped tables — the
    FTS5 search tables and their sync triggers are raw SQL living outside
    that metadata (see wizard.database.create_fts_schema), so they're added
    explicitly here too. Without this, any test exercising search() would
    hit "no such table: note_fts" despite the real (migrated) database
    having it.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        create_fts_schema(conn)
        conn.commit()
    return engine


@pytest.fixture
def db_session(db_engine):
    """Per-test DB session. The engine is also per-test so no rollback tricks needed."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def pseudonym_engine():
    """In-memory SQLite engine with pseudonym_map table for pseudonymisation tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE pseudonym_map ("
            "id INTEGER PRIMARY KEY, "
            "original_hash TEXT NOT NULL UNIQUE, "
            "entity_type TEXT NOT NULL, "
            "fake_value TEXT NOT NULL, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.commit()
    return engine


# ---------------------------------------------------------------------------
# FastMCP app — module-scoped, registered once per test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mcp_app():
    """Import the wizard MCP app with all tools registered.

    Module-scoped: FastMCP registration is global state that only needs to
    happen once per test session.
    """
    import server  # noqa: F401 — registers all tools as a side effect
    from wizard.mcp_instance import mcp
    return mcp


# ---------------------------------------------------------------------------
# FastMCP client — the core fixture for all scenario tests
# ---------------------------------------------------------------------------

# Every module that holds a local reference to get_session / _get_db_session
# that is called inside tool bodies or Depends() providers.
_GET_SESSION_TARGETS = [
    "wizard.tools.session_tools.get_session",
    "wizard.tools.session_helpers.get_session",
    "wizard.tools.task_tools.get_session",
    "wizard.tools.note_tools.get_session",
    "wizard.tools.meeting_tools.get_session",
    "wizard.services.get_session",
    "wizard.middleware.get_session",
    # query_tools and triage_tools use deps.get_db_session (via Depends()).
    # Depends() captures the function object at definition time, so patching
    # the module-level name is ineffective. We patch _get_db_session_impl
    # instead — get_db_session calls it at invocation time, so this works.
    "wizard.deps._get_db_session_impl",
]


def _make_get_session_stub(session: Session):
    """Return a context-manager callable that always yields the given session."""
    @contextmanager
    def _stub() -> Generator[Session, None, None]:
        yield session
    return _stub


class _McpTestClient:
    """Thin wrapper around fastmcp.Client that defaults raise_on_error=False.

    FastMCP's Client.call_tool() defaults to raise_on_error=True — errors raise
    ToolError instead of returning a result with is_error=True. Tests assert on
    is_error, so we default to non-raising to keep assertions uniform.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        return await self._client.call_tool(name, args, raise_on_error=False)

    async def list_tools(self) -> Any:
        return await self._client.list_tools()


@pytest.fixture
async def mcp_client(mcp_app, db_session) -> AsyncGenerator[_McpTestClient, None]:
    """Open a FastMCP in-process client with all DB calls routed to the
    isolated test session.

    call_tool() defaults to raise_on_error=False so tests can assert on
    result.is_error rather than catching exceptions.

    Usage::

        async def test_something(mcp_client):
            result = await mcp_client.call_tool("get_tasks", {})
            assert not result.is_error
            assert "items" in result.structured_content
    """
    stub = _make_get_session_stub(db_session)
    with ExitStack() as stack:
        for target in _GET_SESSION_TARGETS:
            stack.enter_context(patch(target, stub))
        async with Client(mcp_app) as client:
            yield _McpTestClient(client)


# ---------------------------------------------------------------------------
# Repo + security fixtures — kept for tests that exercise non-MCP code
# (analytics, artifact identity, synthesis) and for seed_task in scenarios/conftest.
# ---------------------------------------------------------------------------

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
def session_repo():
    return SessionRepository()


@pytest.fixture
def task_state_repo():
    return TaskStateRepository()
