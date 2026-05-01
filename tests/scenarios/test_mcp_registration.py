"""Scenario: MCP tool registration and schema correctness via FastMCP in-process client.

Uses fastmcp.Client(mcp) — the official FastMCP in-process transport — to exercise
the full FastMCP pipeline (tool registration, schema generation, Depends() wiring)
without spawning a subprocess. Catches issues that direct tool-function calls cannot:
  - Missing or mis-named tool registrations
  - Depends() params leaking into the public schema
  - Type annotation errors that break schema generation
  - Middleware errors on startup
"""

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastmcp.client import Client
from sqlmodel import Session as DBSession
from sqlmodel import SQLModel, create_engine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mcp_app():
    """Import the wizard MCP app with all tools registered.

    Module-scoped: FastMCP registration is global state that only needs to
    happen once per test session.
    """
    import server  # noqa: F401 — side-effectful import that registers all tools
    from wizard.mcp_instance import mcp
    return mcp


@pytest.fixture(scope="module")
def _db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def _db_session(_db_engine):
    connection = _db_engine.connect()
    transaction = connection.begin()
    session = DBSession(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "session_start",
    "session_end",
    "resume_session",
    "task_start",
    "save_note",
    "create_task",
    "update_task",
    "rewind_task",
    "what_am_i_missing",
    "what_should_i_work_on",
    "get_meeting",
    "save_meeting_summary",
    "ingest_meeting",
    "get_tasks",
    "get_task",
    "get_sessions",
    "get_session",
    "get_modes",
    "set_mode",
    "search",
}


@pytest.mark.asyncio
async def test_all_tools_registered(mcp_app):
    """All 20 expected tools are registered — none missing, none phantom."""
    async with Client(mcp_app) as client:
        tools = await client.list_tools()
        registered = {t.name for t in tools}

    assert registered == EXPECTED_TOOLS, (
        f"Missing: {EXPECTED_TOOLS - registered}  |  Unexpected: {registered - EXPECTED_TOOLS}"
    )


# ---------------------------------------------------------------------------
# Schema correctness — Depends() params must not appear in the public schema
# ---------------------------------------------------------------------------

# Maps tool name → required params the LLM must supply.
# Injected Depends() params (t_repo, n_repo, sec, ctx, etc.) must NOT appear.
REQUIRED_PARAMS: dict[str, list[str]] = {
    "session_start": [],
    "session_end": [
        "session_id", "summary", "intent", "working_set",
        "state_delta", "open_loops", "next_actions", "closure_status",
    ],
    "resume_session": [],
    "task_start": ["task_id"],
    "save_note": ["task_id", "note_type", "content"],
    "create_task": ["name"],
    "update_task": ["task_id"],
    "rewind_task": ["task_id"],
    "what_am_i_missing": ["task_id"],
    "what_should_i_work_on": ["session_id"],  # mode has default "focus"
    "get_meeting": ["meeting_id"],
    "save_meeting_summary": ["meeting_id", "summary"],
    "ingest_meeting": ["title", "content"],
    "get_tasks": [],
    "get_task": ["task_id"],
    "get_sessions": [],
    "get_session": ["session_id"],
    "search": ["query"],
}

INJECTED_PARAMS = {
    "ctx", "t_repo", "n_repo", "m_repo", "ts_repo", "sec", "security",
    "session_closer", "session_repo", "task_state_repo", "s_repo", "db",
}


@pytest.mark.asyncio
async def test_tool_schemas_correct(mcp_app):
    """Each tool exposes exactly the expected required params; injected Depends() are hidden."""
    async with Client(mcp_app) as client:
        tools = {t.name: t for t in await client.list_tools()}

    failures = []
    for name, expected_required in REQUIRED_PARAMS.items():
        t = tools[name]
        schema = t.inputSchema
        actual_required = set(schema.get("required", []))
        all_props = set(schema.get("properties", {}).keys())

        if actual_required != set(expected_required):
            failures.append(
                f"{name}: required mismatch — expected {sorted(expected_required)}, "
                f"got {sorted(actual_required)}"
            )

        leaked = all_props & INJECTED_PARAMS
        if leaked:
            failures.append(f"{name}: injected params leaked into schema: {leaked}")

    assert not failures, "\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Live tool call through the full FastMCP pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_tasks_via_mcp_client(mcp_app, _db_session):
    """get_tasks executes end-to-end through the FastMCP pipeline and returns a valid response.

    Uses get_tasks (no session required, read-only) to exercise the full FastMCP
    pipeline — tool dispatch, Depends() resolution, DB query, schema serialisation —
    without the complexity of mocking session lifecycle infrastructure.
    """
    @contextmanager
    def _get_db() -> Generator:
        yield _db_session

    with patch("wizard.tools.query_tools._get_db_session", _get_db):
        async with Client(mcp_app) as client:
            result = await client.call_tool("get_tasks", {})

    assert not result.is_error, f"get_tasks returned error: {result}"
    data = result.structured_content  # parsed dict from FastMCP's structured output
    assert "items" in data, f"items key missing from response: {data}"
    assert isinstance(data["items"], list), f"items is not a list: {data}"
