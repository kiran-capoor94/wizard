"""Shared fixtures for behavioural testing."""

from collections.abc import AsyncGenerator, Generator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp.client import Client
from sqlmodel import Session, SQLModel, create_engine

from wizard.repositories import (
    MeetingRepository,
    NoteRepository,
    SessionRepository,
    TaskRepository,
    TaskStateRepository,
)
from wizard.security import SecurityService


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Fresh in-memory SQLite engine per test — guarantees isolation."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Per-test DB session. The engine is also per-test so no rollback tricks needed."""
    with Session(db_engine) as session:
        yield session


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
