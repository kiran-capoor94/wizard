from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session


def _make_notion_mock(notion=None):
    """Build a notion_client mock. Default: ensure_daily_page raises (non-fatal path)."""
    if notion is not None:
        return notion
    mock = MagicMock()
    mock.ensure_daily_page.side_effect = Exception("notion not configured in tests")
    return mock


def _patch_tools(db_session, sync=None, wb=None, notion=None):
    """Patch tools module dependencies with test doubles. Returns (patches, sync_mock, wb_mock)."""
    sync_mock = sync or MagicMock()
    wb_mock = wb or MagicMock()
    notion_mock = _make_notion_mock(notion)

    patches = {
        "get_session": mock_session(db_session),
        "sync_service": lambda: sync_mock,
        "writeback": lambda: wb_mock,
        "notion_client": lambda: notion_mock,
    }
    return patches, sync_mock, wb_mock


# ---------------------------------------------------------------------------
# session_start
# ---------------------------------------------------------------------------


async def test_session_start_creates_session(db_session):
    from wizard.tools import session_start

    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert result.session_id is not None
    assert result.open_tasks is not None
    assert result.blocked_tasks is not None
    assert result.unsummarised_meetings is not None
    assert result.sync_results is not None


async def test_session_start_calls_sync(db_session):
    from wizard.tools import session_start

    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        await session_start(ctx)

    sync_mock.sync_jira.assert_called_once()
    sync_mock.sync_notion_tasks.assert_called_once()
    sync_mock.sync_notion_meetings.assert_called_once()


async def test_session_start_surfaces_sync_errors(db_session):
    from wizard.tools import session_start

    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(side_effect=Exception("Jira token not configured"))
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert len(result.sync_results) == 3
    jira_sync = result.sync_results[0]
    assert jira_sync.source == "jira"
    assert jira_sync.ok is False
    assert jira_sync.error == "Jira token not configured"
    assert result.sync_results[1].ok is True


async def test_session_start_resolves_daily_page(db_session):
    from wizard.tools import session_start
    from wizard.schemas import DailyPageResult
    from wizard.models import WizardSession

    ctx = MockContext()
    notion_mock = MagicMock()
    notion_mock.ensure_daily_page.return_value = DailyPageResult(
        page_id="today-page-id",
        created=True,
        archived_count=1,
    )

    patches, sync_mock, _ = _patch_tools(db_session, notion=notion_mock)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert result.daily_page is not None
    assert result.daily_page.page_id == "today-page-id"
    assert result.daily_page.created is True

    session = db_session.get(WizardSession, result.session_id)
    assert session.daily_page_id == "today-page-id"


async def test_session_start_daily_page_failure_is_non_fatal(db_session):
    from wizard.tools import session_start

    ctx = MockContext()
    notion_mock = MagicMock()
    notion_mock.ensure_daily_page.side_effect = Exception("notion API down")

    patches, sync_mock, _ = _patch_tools(db_session, notion=notion_mock)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert result.session_id is not None
    assert result.daily_page is None


# ---------------------------------------------------------------------------
# task_start
# ---------------------------------------------------------------------------


async def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from wizard.models import Task, TaskStatus, Note, NoteType
    from wizard.tools import task_start

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(
        note_type=NoteType.INVESTIGATION, content="prior investigation", task_id=task.id
    )
    db_session.add(note)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await task_start(ctx, task_id=task.id)

    assert result.compounding is True
    assert len(result.prior_notes) == 1


async def test_task_start_returns_compounding_false_when_no_notes(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.tools import task_start

    task = Task(name="new task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await task_start(ctx, task_id=task.id)

    assert result.compounding is False


async def test_task_start_raises_when_task_not_found(db_session):
    from fastmcp.exceptions import ToolError
    from wizard.tools import task_start

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError, match="Task 999 not found"):
            await task_start(ctx, task_id=999)


async def test_task_start_latest_mental_model_returns_newest_note_model(db_session):
    import datetime
    from wizard.tools import task_start
    from wizard.models import Task, Note, NoteType

    task = Task(name="state machine refactor")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    # older note — has a mental_model but should NOT be returned
    older_note = Note(
        note_type=NoteType.INVESTIGATION,
        content="earlier investigation",
        task_id=task.id,
        mental_model="Observer pattern",
        created_at=datetime.datetime(2024, 1, 1, 10, 0, 0),
    )
    # newer note — has a mental_model and SHOULD be returned
    newer_note = Note(
        note_type=NoteType.DECISION,
        content="decision made",
        task_id=task.id,
        mental_model="State machine",
        created_at=datetime.datetime(2024, 1, 2, 10, 0, 0),
    )
    db_session.add(older_note)
    db_session.add(newer_note)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await task_start(ctx, task_id=task.id)

    assert result.latest_mental_model == "State machine"


async def test_task_start_latest_mental_model_none_when_no_notes_have_model(db_session):
    from wizard.tools import task_start
    from wizard.models import Task, Note, NoteType

    task = Task(name="simple fix")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(
        note_type=NoteType.INVESTIGATION,
        content="investigation without model",
        task_id=task.id,
        mental_model=None,
    )
    db_session.add(note)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await task_start(ctx, task_id=task.id)

    assert result.latest_mental_model is None


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------


async def test_save_note_scrubs_and_persists(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, Note, NoteType

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="john@example.com found a bug",
        )

    assert result.note_id is not None

    saved_note = db_session.get(Note, result.note_id)
    assert "john@example.com" not in saved_note.content
    assert "[EMAIL_1]" in saved_note.content


# ---------------------------------------------------------------------------
# update_task_status
# ---------------------------------------------------------------------------


async def test_update_task_status_persists_and_writebacks(db_session):
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(
        ok=False,
        error="Task has no notion_id",
    )

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None
    task_id = task.id

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task_status(
            ctx, task_id=task_id, new_status=TaskStatus.DONE
        )

    assert result.new_status == TaskStatus.DONE
    assert result.jira_write_back.ok is True
    assert result.notion_write_back.ok is False
    assert result.notion_write_back.error == "Task has no notion_id"

    task_fresh = db_session.get(Task, task_id)
    assert task_fresh.status == TaskStatus.DONE


async def test_update_task_status_dual_writeback(db_session):
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    task = Task(name="fix", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task_status(
            ctx, task_id=task.id, new_status=TaskStatus.DONE
        )

    assert result.jira_write_back.ok is True
    assert result.notion_write_back.ok is True


# ---------------------------------------------------------------------------
# get_meeting
# ---------------------------------------------------------------------------


async def test_get_meeting_returns_content_and_open_tasks(db_session):
    from wizard.tools import get_meeting
    from wizard.models import Task, TaskStatus, Meeting, MeetingTasks

    task = Task(name="fix auth", status=TaskStatus.IN_PROGRESS)
    meeting = Meeting(title="standup", content="we discussed fix auth")
    db_session.add(task)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(meeting)
    assert task.id is not None
    assert meeting.id is not None

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await get_meeting(ctx, meeting_id=meeting.id)

    assert result.meeting_id == meeting.id
    assert result.already_summarised is False
    assert len(result.open_tasks) == 1


# ---------------------------------------------------------------------------
# save_meeting_summary
# ---------------------------------------------------------------------------


async def test_save_meeting_summary_scrubs_and_persists(db_session):
    from wizard.tools import save_meeting_summary
    from wizard.models import WizardSession, Meeting, Note
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    meeting = Meeting(title="standup", content="notes")
    db_session.add(session)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(meeting)
    assert session.id is not None
    assert meeting.id is not None

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await save_meeting_summary(
            ctx,
            meeting_id=meeting.id,
            summary="patient 943 476 5919 was discussed",
        )

    assert result.note_id is not None

    saved = db_session.get(Note, result.note_id)
    assert "943 476 5919" not in saved.content
    assert "[NHS_ID_1]" in saved.content


async def test_save_meeting_summary_tasks_linked_count(db_session):
    from wizard.tools import save_meeting_summary
    from wizard.models import WizardSession, Meeting, Task
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    meeting = Meeting(title="sprint review", content="discussed items")
    task1 = Task(name="task one")
    task2 = Task(name="task two")
    db_session.add(session)
    db_session.add(meeting)
    db_session.add(task1)
    db_session.add(task2)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(meeting)
    db_session.refresh(task1)
    db_session.refresh(task2)
    assert session.id is not None
    assert meeting.id is not None
    assert task1.id is not None
    assert task2.id is not None

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await save_meeting_summary(
            ctx,
            meeting_id=meeting.id,
            summary="sprint summary",
            task_ids=[task1.id, task2.id],
        )

    assert result.tasks_linked == 2


# ---------------------------------------------------------------------------
# session_end
# ---------------------------------------------------------------------------


async def test_session_end_saves_summary_note(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession, Note, NoteType
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession(daily_page_id="test-daily-page")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None
    session_id = session.id

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await session_end(
            ctx,
            session_id=session_id,
            summary="wrapped up today's work",
            intent="wrapped up",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    assert result.note_id is not None
    assert result.notion_write_back.ok is True

    saved = db_session.get(Note, result.note_id)
    assert saved.note_type == NoteType.SESSION_SUMMARY
    assert saved.session_id == session_id

    wb_mock.push_session_summary.assert_called_once()
    called_session = wb_mock.push_session_summary.call_args[0][0]
    assert called_session.daily_page_id == "test-daily-page"


async def test_session_end_session_state_saved_true_on_happy_path(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="wrapped up",
            intent="finish auth refactor",
            working_set=[1, 2],
            state_delta="Completed token refresh logic",
            open_loops=["rate limiting"],
            next_actions=["write tests"],
            closure_status="clean",
        )

    assert result.session_state_saved is True


async def test_session_end_session_state_saved_false_when_write_fails(db_session):
    from unittest.mock import patch as _patch
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        with _patch(
            "wizard.schemas.SessionState.model_dump_json",
            side_effect=RuntimeError("disk full"),
        ):
            result = await session_end(
                ctx,
                session_id=session.id,
                summary="wrapped up",
                intent="test",
                working_set=[],
                state_delta="none",
                open_loops=[],
                next_actions=[],
                closure_status="clean",
            )

    assert result.session_state_saved is False


# ---------------------------------------------------------------------------
# ingest_meeting
# ---------------------------------------------------------------------------


async def test_ingest_meeting_creates_meeting(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import Meeting, MeetingCategory
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True,
        page_id="notion-meeting-page-id",
    )

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await ingest_meeting(
            ctx,
            title="Sprint Planning",
            content="john@example.com reported a bug",
            source_id="krisp-abc",
            source_url="https://krisp.ai/m/abc",
            category=MeetingCategory.PLANNING,
        )

    assert result.meeting_id is not None
    assert result.already_existed is False
    meeting = db_session.get(Meeting, result.meeting_id)
    assert "john@example.com" not in meeting.content
    assert "[EMAIL_1]" in meeting.content


async def test_ingest_meeting_dedup_by_source_id(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import Meeting
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True,
        page_id="notion-meeting-page-id",
    )

    existing = Meeting(title="Old", content="old", source_id="krisp-abc")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await ingest_meeting(
            ctx, title="New", content="new", source_id="krisp-abc"
        )

    assert result.already_existed is True
    assert result.meeting_id == existing.id


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


async def test_create_task_creates_and_links(db_session):
    from wizard.tools import create_task
    from wizard.models import Meeting, Task, TaskStatus, TaskPriority, MeetingTasks
    from wizard.schemas import WriteBackStatus
    from sqlmodel import select

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(
        ok=True,
        page_id="notion-task-page-id",
    )

    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    meeting_id = meeting.id

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await create_task(
            ctx,
            name="Fix john@example.com auth bug",
            priority=TaskPriority.HIGH,
            meeting_id=meeting_id,
        )

    assert result.task_id is not None
    assert result.notion_write_back.ok is True
    task = db_session.get(Task, result.task_id)
    assert "john@example.com" not in task.name
    assert task.status == TaskStatus.TODO

    link = db_session.exec(
        select(MeetingTasks).where(
            MeetingTasks.task_id == task.id,
            MeetingTasks.meeting_id == meeting_id,
        )
    ).first()
    assert link is not None


async def test_create_task_creates_paired_task_state(db_session):
    from wizard.tools import create_task
    from wizard.models import TaskState
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(ok=True)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        response = await create_task(ctx, name="new task")

    state = db_session.get(TaskState, response.task_id)
    assert state is not None
    assert state.note_count == 0
    assert state.decision_count == 0


# ---------------------------------------------------------------------------
# End-to-end compounding loop (design spec Section 10)
# ---------------------------------------------------------------------------


async def test_compounding_loop_across_two_sessions(db_session):
    """Proves the full compounding context loop:
    session 1: session_start -> task_start -> save_note -> update_task_status -> session_end
    session 2: session_start -> task_start returns compounding=True with prior notes
    """
    from wizard.tools import (
        session_start,
        task_start,
        save_note,
        update_task_status,
        session_end,
    )
    from wizard.models import Task, TaskStatus, NoteType

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
    patches, _, _ = _patch_tools(db_session, sync=sync_mock, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        # --- Session 1 ---
        s1 = await session_start(ctx)
        session_id = s1.session_id

        # task_start -- no prior notes yet
        ts1 = await task_start(ctx, task_id=task_id)
        assert ts1.compounding is False

        # save_note
        await save_note(
            ctx,
            task_id=task_id,
            note_type=NoteType.INVESTIGATION,
            content="Found the root cause",
        )

        # update_task_status
        await update_task_status(
            ctx, task_id=task_id, new_status=TaskStatus.IN_PROGRESS
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
        )

        # --- Session 2 ---
        s2 = await session_start(ctx)
        assert s2.session_id != session_id

        # task_start -- should see prior notes now
        ts2 = await task_start(ctx, task_id=task_id)
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
# ToolCall telemetry
# ---------------------------------------------------------------------------


async def test_session_start_logs_tool_call(db_session):
    from wizard.tools import session_start
    from wizard.models import ToolCall
    from sqlmodel import select

    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "session_start"
    assert rows[0].session_id == result.session_id


async def test_task_start_logs_tool_call_without_session_id(db_session):
    from wizard.tools import task_start
    from wizard.models import Task, ToolCall
    from sqlmodel import select

    task = Task(name="test", source_id="T-1", source_type="JIRA")
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        await task_start(ctx, task_id=task.id)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "task_start"
    assert rows[0].session_id is None


async def test_session_end_logs_tool_call_with_session_id(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession, ToolCall
    from sqlmodel import select

    session = WizardSession(daily_page_id="p-1")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    from wizard.schemas import WriteBackStatus

    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="done",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "session_end"
    assert rows[0].session_id == session.id


async def test_ingest_meeting_logs_tool_call_without_session_id(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import ToolCall
    from sqlmodel import select

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    from wizard.schemas import WriteBackStatus

    wb_mock.push_meeting_to_notion = MagicMock(
        return_value=WriteBackStatus(ok=False, error="no token")
    )

    with patch.multiple("wizard.tools", **patches):
        await ingest_meeting(ctx, title="standup", content="transcript here")

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "ingest_meeting"
    assert rows[0].session_id is None


async def test_tool_call_sequence_within_session(db_session):
    """session_start -> save_note -> session_end produces ordered ToolCall rows."""
    from wizard.tools import session_start, save_note, session_end
    from wizard.models import Task, ToolCall, NoteType
    from wizard.schemas import WriteBackStatus
    from sqlmodel import col, select

    task = Task(name="test", source_id="T-1", source_type="JIRA")
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, sync_mock, wb_mock = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        s = await session_start(ctx)
        await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="finding",
        )
        await session_end(
            ctx,
            session_id=s.session_id,
            summary="wrap up",
            intent="wrap up",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    rows = db_session.exec(select(ToolCall).order_by(col(ToolCall.called_at))).all()
    names = [r.tool_name for r in rows]
    assert names == ["session_start", "save_note", "session_end"]
    assert rows[0].session_id == s.session_id
    assert (
        rows[1].session_id == s.session_id
    )  # ctx state carries session_id into save_note
    assert rows[2].session_id == s.session_id


# ---------------------------------------------------------------------------
# save_note — mental_model and TaskState wiring
# ---------------------------------------------------------------------------


async def test_save_note_stores_mental_model_when_provided(db_session):
    from wizard.tools import save_note
    from wizard.models import Note, NoteType, Task

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        response = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Race condition between token refresh and request",
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model == "Race condition between token refresh and request"
    assert response.mental_model_saved is True


async def test_save_note_leaves_mental_model_null_when_not_provided(db_session):
    from wizard.tools import save_note
    from wizard.models import Note, NoteType, Task

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        response = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="ref material",
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model is None
    assert response.mental_model_saved is False


async def test_save_note_mental_model_saved_true_when_model_provided(db_session):
    from wizard.tools import save_note
    from wizard.models import NoteType, Task

    task = Task(name="t2")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="some investigation",
            mental_model="State machine pattern",
        )

    assert result.mental_model_saved is True


async def test_save_note_mental_model_saved_false_when_model_absent(db_session):
    from wizard.tools import save_note
    from wizard.models import NoteType, Task

    task = Task(name="t3")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="some docs",
            mental_model=None,
        )

    assert result.mental_model_saved is False


async def test_save_note_updates_task_state(db_session):
    from wizard.tools import save_note
    from wizard.models import NoteType, Task, TaskState
    from wizard.deps import task_state_repo

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    # Pre-create the TaskState row so we can refresh it from the same session.
    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        await save_note(ctx, task_id=task.id, note_type=NoteType.DECISION, content="d")

    state = db_session.get(TaskState, task.id)
    db_session.refresh(state)
    assert state is not None
    assert state.note_count == 1
    assert state.decision_count == 1
    assert state.last_note_at is not None


# ---------------------------------------------------------------------------
# update_task_status — TaskState wiring
# ---------------------------------------------------------------------------


async def test_update_task_status_records_last_status_change_at(db_session):
    import datetime as _dt
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskState, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.deps import task_state_repo

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None
    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        await update_task_status(
            ctx, task_id=task.id, new_status=TaskStatus.IN_PROGRESS
        )

    state = db_session.get(TaskState, task.id)
    db_session.refresh(state)
    assert state is not None
    assert state.last_status_change_at is not None
    delta = _dt.datetime.now() - state.last_status_change_at
    assert delta.total_seconds() < 5


async def test_update_task_status_does_not_reset_stale_days(db_session):
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskState, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    task = Task(name="t", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    state = TaskState(
        task_id=task.id,
        last_touched_at=task.created_at,
        stale_days=7,
        note_count=3,
        decision_count=1,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        await update_task_status(ctx, task_id=task.id, new_status=TaskStatus.DONE)

    db_session.refresh(state)
    assert state.stale_days == 7
    assert state.note_count == 3


# ---------------------------------------------------------------------------
# rewind_task
# ---------------------------------------------------------------------------


async def test_rewind_task_empty_timeline(db_session):
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskStatus
    from wizard.deps import task_state_repo

    task = Task(name="empty task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await rewind_task(ctx, task_id=task.id)

    assert result.timeline == []
    assert result.summary.total_notes == 0
    assert result.summary.duration_days == 0


# --- session threading ---


async def test_session_start_sets_current_session_id_in_ctx_state(db_session):
    from wizard.tools import session_start

    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    ctx = MockContext()
    with patch.multiple("wizard.tools", **patches):
        result = await session_start(ctx)

    assert await ctx.get_state("current_session_id") == result.session_id


async def test_save_note_uses_session_id_from_ctx_state_when_set(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType, Note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    await ctx.set_state("current_session_id", 42)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.DOCS, content="content"
        )

    note = db_session.get(Note, result.note_id)
    assert note.session_id == 42


async def test_save_note_session_id_null_when_no_ctx_state(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType, Note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()  # no set_state called

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.DOCS, content="content"
        )

    note = db_session.get(Note, result.note_id)
    assert note.session_id is None


async def test_session_end_clears_current_session_id_from_ctx_state(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    await ctx.set_state("current_session_id", session.id)

    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="done",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    assert await ctx.get_state("current_session_id") is None


# --- progress ---


async def test_session_start_reports_progress(db_session):
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    impl = _MockContextImpl()
    ctx = mock_ctx(impl)
    with patch.multiple("wizard.tools", **patches):
        from wizard.tools import session_start

        await session_start(ctx)

    assert len(impl.progress_calls) == 4
    assert impl.progress_calls[0] == (0, 3, "Syncing Jira...")
    assert impl.progress_calls[1] == (1, 3, "Syncing Notion tasks...")
    assert impl.progress_calls[2] == (2, 3, "Syncing Notion meetings...")
    assert impl.progress_calls[3] == (3, 3, "Sync complete.")


# --- elicitation: save_note ---


async def test_save_note_elicits_mental_model_for_investigation(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType, Note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="I now understand the root cause is X")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="looked at logs",
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "I now understand the root cause is X"


async def test_save_note_elicits_mental_model_for_decision(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType, Note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="We chose approach B for simplicity")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.DECISION, content="chose B"
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "We chose approach B for simplicity"


async def test_save_note_does_not_elicit_for_docs_notes(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType, Note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="should not be used")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx, task_id=task.id, note_type=NoteType.DOCS, content="docs"
        )

    note = db_session.get(Note, result.note_id)
    # DOCS note: elicit should NOT have been called, mental_model stays None
    assert note.mental_model is None


async def test_save_note_mental_model_param_skips_elicitation(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType, Note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="this should not win")

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
            mental_model="caller provided this",
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "caller provided this"


async def test_save_note_handles_elicit_failure_gracefully(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, TaskStatus, NoteType

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(supports_elicit=False)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
        )

    assert result.note_id is not None  # tool succeeded despite elicit failure


# --- elicitation: update_task_status ---


async def test_update_task_status_elicits_outcome_when_done(db_session):
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    task = Task(name="task", status=TaskStatus.IN_PROGRESS, notion_id="notion-page-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="Shipped the fix to production.")
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.append_task_outcome.return_value = WriteBackStatus(ok=True)

    with patch.multiple("wizard.tools", **patches):
        await update_task_status(ctx, task_id=task.id, new_status=TaskStatus.DONE)

    wb_mock.append_task_outcome.assert_called_once()
    call_args = wb_mock.append_task_outcome.call_args
    assert "Shipped the fix" in call_args[0][1]


async def test_update_task_status_does_not_elicit_for_in_progress(db_session):
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    task = Task(name="task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="should not be called")
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    with patch.multiple("wizard.tools", **patches):
        await update_task_status(
            ctx, task_id=task.id, new_status=TaskStatus.IN_PROGRESS
        )

    wb_mock.append_task_outcome.assert_not_called()


# --- session_end expansion ---


async def test_session_end_persists_session_state(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import SessionState, WriteBackStatus
    import json

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="good session",
            intent="shipped the auth fix",
            working_set=[1, 2],
            state_delta="ENG-42 now done",
            open_loops=["follow up with team"],
            next_actions=["write tests for ENG-50"],
            closure_status="clean",
        )

    db_session.refresh(session)
    assert session.session_state is not None
    state = SessionState.model_validate_json(session.session_state)
    assert state.intent == "shipped the auth fix"
    assert state.working_set == [1, 2]
    assert state.closure_status == "clean"
    assert state.open_loops == ["follow up with team"]
    assert state.next_actions == ["write tests for ENG-50"]

    assert result.closure_status == "clean"
    assert result.open_loops_count == 1
    assert result.next_actions_count == 1
    assert result.intent == "shipped the auth fix"


async def test_session_end_emits_confirmation_via_ctx_info(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    impl = _MockContextImpl()
    ctx = mock_ctx(impl)
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="intent",
            working_set=[],
            state_delta="nothing",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
        )

    assert any("clean" in msg for msg in impl.info_calls)


async def test_session_end_rejects_invalid_closure_status(db_session):
    from fastmcp.exceptions import ToolError
    from wizard.tools import session_end
    from wizard.models import WizardSession

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    patches, _, wb_mock = _patch_tools(db_session)
    wb_mock.push_session_summary = MagicMock()

    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError):
            await session_end(
                ctx,
                session_id=session.id,
                summary="done",
                intent="intent",
                working_set=[],
                state_delta="nothing",
                open_loops=[],
                next_actions=[],
                closure_status="invalid_value",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# ToolCall session_id linkage for create_task and ingest_meeting
# ---------------------------------------------------------------------------


async def test_create_task_links_tool_call_to_active_session(db_session):
    from wizard.tools import create_task
    from wizard.models import ToolCall, WizardSession
    from wizard.schemas import WriteBackStatus
    from sqlmodel import select

    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(
        ok=False, error="no notion"
    )
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        await create_task(ctx, name="new task")

    rows = list(db_session.execute(select(ToolCall)).scalars().all())
    assert len(rows) == 1
    assert rows[0].session_id == session.id


async def test_ingest_meeting_links_tool_call_to_active_session(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import ToolCall, WizardSession
    from wizard.schemas import WriteBackStatus
    from sqlmodel import select

    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=False, error="no notion"
    )
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        await ingest_meeting(ctx, title="standup", content="discussed items")

    rows = list(db_session.execute(select(ToolCall)).scalars().all())
    assert len(rows) == 1
    assert rows[0].session_id == session.id


# ---------------------------------------------------------------------------
# save_meeting_summary reads session_id from ctx state
# ---------------------------------------------------------------------------


async def test_save_meeting_summary_reads_session_id_from_ctx_state(db_session):
    """session_id must come from ctx state, not as an explicit parameter."""
    from wizard.tools import save_meeting_summary
    from wizard.models import WizardSession, Meeting, Note
    from wizard.schemas import WriteBackStatus

    session = WizardSession()
    meeting = Meeting(title="planning", content="content")
    db_session.add(session)
    db_session.add(meeting)
    db_session.flush()
    db_session.refresh(session)
    db_session.refresh(meeting)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)

    wb_mock = MagicMock()
    wb_mock.push_meeting_summary.return_value = WriteBackStatus(ok=True)
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await save_meeting_summary(
            ctx,
            meeting_id=meeting.id,
            summary="planning notes",
        )

    saved = db_session.get(Note, result.note_id)
    assert saved.session_id == session.id


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------


async def test_update_task_updates_single_field(db_session):
    from wizard.tools import update_task
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_due_date.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(
            ctx, task_id=task.id, due_date="2026-04-17T14:00:00Z"
        )

    assert result.task_id == task.id
    assert "due_date" in result.updated_fields
    assert len(result.updated_fields) == 1

    db_session.refresh(task)
    assert task.due_date is not None


async def test_update_task_updates_multiple_fields(db_session):
    from wizard.tools import update_task
    from wizard.models import Task, TaskPriority, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_priority.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
        )

    assert set(result.updated_fields) == {"status", "priority"}
    assert result.task_state_updated is True

    db_session.refresh(task)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.priority == TaskPriority.HIGH


async def test_update_task_raises_when_no_fields(db_session):
    from wizard.tools import update_task
    from wizard.models import Task
    from fastmcp.exceptions import ToolError

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError, match="At least one field"):
            await update_task(ctx, task_id=task.id)


async def test_update_task_status_triggers_writebacks(db_session):
    from wizard.tools import update_task
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", source_id="ENG-1", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(ctx, task_id=task.id, status=TaskStatus.IN_PROGRESS)

    assert result.status_writeback is not None
    assert result.status_writeback.ok is True
    wb_mock.push_task_status.assert_called_once()
    wb_mock.push_task_status_to_notion.assert_called_once()


async def test_update_task_done_elicits_outcome(db_session):
    from wizard.tools import update_task
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    task = Task(name="test", status=TaskStatus.IN_PROGRESS, notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.append_task_outcome.return_value = WriteBackStatus(ok=True)

    ctx = MockContext(elicit_response="Completed successfully")
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        await update_task(ctx, task_id=task.id, status=TaskStatus.DONE)

    wb_mock.append_task_outcome.assert_called_once()


async def test_update_task_done_without_notion_id_skips_elicit(db_session):
    from wizard.tools import update_task
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    task = Task(name="test", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    ctx = MockContext(elicit_response="should not be used")
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        await update_task(ctx, task_id=task.id, status=TaskStatus.DONE)

    wb_mock.append_task_outcome.assert_not_called()


async def test_update_task_invalid_due_date_format(db_session):
    from wizard.tools import update_task
    from wizard.models import Task
    from fastmcp.exceptions import ToolError

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError, match="Invalid due_date format"):
            await update_task(ctx, task_id=task.id, due_date="not-a-date")


async def test_update_task_name_is_scrubbed(db_session):
    from wizard.tools import update_task
    from wizard.models import Task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        await update_task(ctx, task_id=task.id, name="john@example.com reported bug")

    db_session.refresh(task)
    assert "john@example.com" not in task.name
    assert "[EMAIL_1]" in task.name


async def test_update_task_due_date_writeback(db_session):
    from wizard.tools import update_task
    from wizard.models import Task
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_due_date.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(
            ctx, task_id=task.id, due_date="2026-04-17T14:00:00Z"
        )

    assert result.due_date_writeback is not None
    assert result.due_date_writeback.ok is True
    wb_mock.push_task_due_date.assert_called_once()


async def test_update_task_priority_writeback(db_session):
    from wizard.tools import update_task
    from wizard.models import Task, TaskPriority
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_priority.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(ctx, task_id=task.id, priority=TaskPriority.HIGH)

    assert result.priority_writeback is not None
    assert result.priority_writeback.ok is True
    wb_mock.push_task_priority.assert_called_once()


async def test_update_task_notion_id(db_session):
    from wizard.tools import update_task
    from wizard.models import Task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(ctx, task_id=task.id, notion_id="notion-456")

    assert "notion_id" in result.updated_fields
    db_session.refresh(task)
    assert task.notion_id == "notion-456"


async def test_update_task_status_deprecated(db_session, caplog):
    import logging
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO, source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        with caplog.at_level(logging.WARNING):
            result = await update_task_status(
                ctx, task_id=task.id, new_status=TaskStatus.IN_PROGRESS
            )

    assert "deprecated" in caplog.text.lower()
    assert result.deprecation_warning is not None
    assert "update_task" in result.deprecation_warning


async def test_update_task_source_url(db_session):
    from wizard.tools import update_task
    from wizard.models import Task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(
            ctx,
            task_id=task.id,
            source_url="https://github.com/org/repo/issues/123",
        )

    assert "source_url" in result.updated_fields
    db_session.refresh(task)
    assert task.source_url == "https://github.com/org/repo/issues/123"


# ---------------------------------------------------------------------------
# Fix 2: update_task outcome writeback called before context exits (no double-commit)
# ---------------------------------------------------------------------------


async def test_update_task_outcome_writeback_called_when_elicited(db_session):
    """Outcome writeback must be called when elicitation returns text."""
    from wizard.tools import update_task
    from wizard.models import Task, TaskStatus, TaskPriority, TaskCategory, TaskState
    import datetime

    task = Task(
        name="Fix auth",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        notion_id="notion-page-123",
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    state = TaskState(
        task_id=task.id,
        note_count=0,
        decision_count=0,
        last_touched_at=datetime.datetime.now(),
        stale_days=0,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext(elicit_response="Shipped the fix.")
    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = MagicMock(ok=True, error=None)
    wb_mock.push_task_status_to_notion.return_value = MagicMock(ok=True, error=None, page_id="notion-page-123")
    wb_mock.append_task_outcome.return_value = MagicMock(ok=True, error=None)

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = await update_task(ctx, task_id=task.id, status=TaskStatus.DONE)

    wb_mock.append_task_outcome.assert_called_once()
    call_args = wb_mock.append_task_outcome.call_args
    assert "Shipped the fix." in call_args[0][1]
    assert result.updated_fields == ["status"]


# ---------------------------------------------------------------------------
# Fix 1: rewind_task + what_am_i_missing session linkage
# ---------------------------------------------------------------------------


async def test_rewind_task_links_tool_call_to_session(db_session):
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskStatus, ToolCall
    from wizard.deps import task_state_repo
    from sqlmodel import select

    task = Task(name="linked task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_state_repo().create_for_task(db_session, task)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = 99
    ctx = mock_ctx(impl)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        await rewind_task(ctx, task_id=task.id)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "rewind_task"
    assert rows[0].session_id == 99


async def test_what_am_i_missing_links_tool_call_to_session(db_session):
    from wizard.tools import what_am_i_missing
    from wizard.models import Task, TaskStatus, ToolCall
    from wizard.deps import task_state_repo
    from sqlmodel import select

    task = Task(name="gap task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_state_repo().create_for_task(db_session, task)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = 77
    ctx = mock_ctx(impl)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        await what_am_i_missing(ctx, task_id=task.id)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "what_am_i_missing"
    assert rows[0].session_id == 77


# ---------------------------------------------------------------------------
# Fix 2: resume_session links ToolCall to new session
# ---------------------------------------------------------------------------


async def test_resume_session_links_tool_call_to_new_session(db_session):
    from wizard.tools import resume_session
    from wizard.models import WizardSession, Note, NoteType, ToolCall
    from sqlmodel import select

    prior = WizardSession()
    db_session.add(prior)
    db_session.flush()
    db_session.refresh(prior)
    note = Note(note_type=NoteType.DOCS, content="prior note", session_id=prior.id)
    db_session.add(note)
    db_session.flush()

    ctx = MockContext()
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        result = await resume_session(ctx)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "resume_session"
    # Must be linked to the *new* session, not the prior one and not None
    assert rows[0].session_id == result.session_id
    assert rows[0].session_id != prior.id


# ---------------------------------------------------------------------------
# Fix 5: save_note always scrubs mental_model
# ---------------------------------------------------------------------------


async def test_save_note_scrubs_mental_model_when_passed_directly(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, NoteType, Note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Spoke with john@example.com about the issue",
        )

    note = db_session.get(Note, result.note_id)
    assert note is not None
    assert "john@example.com" not in note.mental_model
    assert "[EMAIL_1]" in note.mental_model
