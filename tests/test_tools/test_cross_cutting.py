from unittest.mock import MagicMock, patch

from tests.helpers import MockContext, mock_session


def _make_notion_mock(notion=None):
    """Build a notion_client mock. Default: ensure_daily_page raises (non-fatal path)."""
    import httpx
    if notion is not None:
        return notion
    mock = MagicMock()
    mock.ensure_daily_page.side_effect = httpx.HTTPError("notion not configured in tests")
    return mock


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# End-to-end compounding loop (design spec Section 10)
# ---------------------------------------------------------------------------


async def test_compounding_loop_across_two_sessions(db_session):
    """Proves the full compounding context loop:
    session 1: session_start -> task_start -> save_note -> update_task -> session_end
    session 2: session_start -> task_start returns compounding=True with prior notes
    """
    from wizard.models import NoteType, Task, TaskStatus
    from wizard.tools import (
        save_note,
        session_end,
        session_start,
        task_start,
        update_task,
    )

    # Seed a task (simulating what sync would produce)
    task = Task(name="Fix auth", source_id="ENG-100", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None
    task_id: int = task.id

    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(
        ok=False,
        error="Task has no notion_id",
    )
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)
    sync_mock = MagicMock()
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import (
            MeetingRepository,
            NoteRepository,
            TaskRepository,
            TaskStateRepository,
        )
        from wizard.security import SecurityService

        # --- Session 1 ---
        s1 = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )
        session_id = s1.session_id

        # task_start -- no prior notes yet
        ts1 = await task_start(ctx, task_id=task_id, t_repo=TaskRepository(), n_repo=NoteRepository())
        assert ts1.compounding is False

        # save_note
        await save_note(
            ctx,
            task_id=task_id,
            note_type=NoteType.INVESTIGATION,
            content="Found the root cause",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

        # update_task
        await update_task(
            ctx,
            task_id=task_id,
            status=TaskStatus.IN_PROGRESS,
            t_repo=TaskRepository(),
            t_state_repo=TaskStateRepository(),
            sec=SecurityService(),
            wb=wb_mock,
        )

        # session_end
        await session_end(
            ctx,
            session_id=session_id,
            summary="Investigated auth bug",
            intent="investigate auth",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

        # --- Session 2 ---
        s2 = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )
        assert s2.session_id != session_id

        # task_start -- should see prior notes now
        ts2 = await task_start(ctx, task_id=task_id, t_repo=TaskRepository(), n_repo=NoteRepository())
        assert ts2.compounding is True
        assert len(ts2.prior_notes) >= 1
        assert ts2.notes_by_type["investigation"] >= 1


# ---------------------------------------------------------------------------
# Spike: FastMCP serializes Pydantic models directly
# ---------------------------------------------------------------------------


def test_fastmcp_serializes_pydantic_models():
    """Spike: verify FastMCP 3.2.0+ can serialize our response models without .model_dump()."""
    from fastmcp import FastMCP

    from wizard.schemas import SessionStartResponse, SourceSyncStatus

    test_mcp = FastMCP("test")

    @test_mcp.tool()
    def test_tool() -> SessionStartResponse:
        return SessionStartResponse(
            session_id=1,
            open_tasks=[],
            blocked_tasks=[],
            unsummarised_meetings=[],
            sync_results=[SourceSyncStatus(source="jira", ok=True)],
        )

    assert test_tool is not None


# ---------------------------------------------------------------------------
# ToolCall telemetry — middleware unit tests
# ---------------------------------------------------------------------------


async def test_middleware_writes_tool_call_row(db_session):
    """ToolLoggingMiddleware writes a ToolCall row on every tool invocation."""
    from unittest.mock import AsyncMock

    from sqlmodel import select

    from wizard.middleware import ToolLoggingMiddleware
    from wizard.models import ToolCall

    middleware = ToolLoggingMiddleware()

    # Build a minimal MiddlewareContext-like mock
    context = MagicMock()
    context.message.name = "session_start"
    context.fastmcp_context.get_state = AsyncMock(return_value=42)

    call_next = AsyncMock(return_value=MagicMock())

    with patch("wizard.middleware.get_session", mock_session(db_session)):
        await middleware.on_call_tool(context, call_next)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "session_start"
    assert rows[0].session_id == 42
    call_next.assert_awaited_once_with(context)


async def test_middleware_writes_tool_call_row_without_session(db_session):
    """ToolLoggingMiddleware writes a ToolCall row with session_id=None when no session active."""
    from unittest.mock import AsyncMock

    from sqlmodel import select

    from wizard.middleware import ToolLoggingMiddleware
    from wizard.models import ToolCall

    middleware = ToolLoggingMiddleware()

    context = MagicMock()
    context.message.name = "task_start"
    context.fastmcp_context.get_state = AsyncMock(side_effect=Exception("no state"))

    call_next = AsyncMock(return_value=MagicMock())

    with patch("wizard.middleware.get_session", mock_session(db_session)):
        await middleware.on_call_tool(context, call_next)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "task_start"
    assert rows[0].session_id is None
