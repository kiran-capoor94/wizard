from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import mock_session


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

def test_session_start_creates_session(db_session):
    from wizard.tools import session_start
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        result = session_start()

    assert result.session_id is not None
    assert result.open_tasks is not None
    assert result.blocked_tasks is not None
    assert result.unsummarised_meetings is not None
    assert result.sync_results is not None


def test_session_start_calls_sync(db_session):
    from wizard.tools import session_start
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        session_start()

    sync_mock.sync_all.assert_called_once()


def test_session_start_surfaces_sync_errors(db_session):
    from wizard.tools import session_start
    from wizard.schemas import SourceSyncStatus
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[
        SourceSyncStatus(source="jira", ok=False, error="Jira token not configured"),
        SourceSyncStatus(source="notion_tasks", ok=True),
        SourceSyncStatus(source="notion_meetings", ok=True),
    ])

    with patch.multiple("wizard.tools", **patches):
        result = session_start()

    assert len(result.sync_results) == 3
    jira_sync = result.sync_results[0]
    assert jira_sync.source == "jira"
    assert jira_sync.ok is False
    assert jira_sync.error == "Jira token not configured"
    assert result.sync_results[1].ok is True


def test_session_start_resolves_daily_page(db_session):
    from wizard.tools import session_start
    from wizard.schemas import DailyPageResult
    from wizard.models import WizardSession

    notion_mock = MagicMock()
    notion_mock.ensure_daily_page.return_value = DailyPageResult(
        page_id="today-page-id",
        created=True,
        archived_count=1,
    )

    patches, sync_mock, _ = _patch_tools(db_session, notion=notion_mock)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        result = session_start()

    assert result.daily_page is not None
    assert result.daily_page.page_id == "today-page-id"
    assert result.daily_page.created is True

    session = db_session.get(WizardSession, result.session_id)
    assert session.daily_page_id == "today-page-id"


def test_session_start_daily_page_failure_is_non_fatal(db_session):
    from wizard.tools import session_start

    notion_mock = MagicMock()
    notion_mock.ensure_daily_page.side_effect = Exception("notion API down")

    patches, sync_mock, _ = _patch_tools(db_session, notion=notion_mock)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        result = session_start()

    assert result.session_id is not None
    assert result.daily_page is None


# ---------------------------------------------------------------------------
# task_start
# ---------------------------------------------------------------------------

def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from wizard.models import Task, TaskStatus, Note, NoteType
    from wizard.tools import task_start

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(note_type=NoteType.INVESTIGATION, content="prior investigation", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = task_start(task_id=task.id)

    assert result.compounding is True
    assert len(result.prior_notes) == 1


def test_task_start_returns_compounding_false_when_no_notes(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.tools import task_start

    task = Task(name="new task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = task_start(task_id=task.id)

    assert result.compounding is False


def test_task_start_raises_when_task_not_found(db_session):
    from fastmcp.exceptions import ToolError
    from wizard.tools import task_start
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError, match="Task 999 not found"):
            task_start(task_id=999)


def test_task_start_latest_mental_model_returns_newest_note_model(db_session):
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

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = task_start(task_id=task.id)

    assert result.latest_mental_model == "State machine"


def test_task_start_latest_mental_model_none_when_no_notes_have_model(db_session):
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

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = task_start(task_id=task.id)

    assert result.latest_mental_model is None


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------

def test_save_note_scrubs_and_persists(db_session):
    from wizard.tools import save_note
    from wizard.models import Task, Note, NoteType

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = save_note(
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

def test_update_task_status_persists_and_writebacks(db_session):
    from wizard.tools import update_task_status
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(
        ok=False, error="Task has no notion_id",
    )

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None
    task_id = task.id

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = update_task_status(task_id=task_id, new_status=TaskStatus.DONE)

    assert result.new_status == TaskStatus.DONE
    assert result.jira_write_back.ok is True
    assert result.notion_write_back.ok is False
    assert result.notion_write_back.error == "Task has no notion_id"

    task_fresh = db_session.get(Task, task_id)
    assert task_fresh.status == TaskStatus.DONE


def test_update_task_status_dual_writeback(db_session):
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

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = update_task_status(task_id=task.id, new_status=TaskStatus.DONE)

    assert result.jira_write_back.ok is True
    assert result.notion_write_back.ok is True


# ---------------------------------------------------------------------------
# get_meeting
# ---------------------------------------------------------------------------

def test_get_meeting_returns_content_and_open_tasks(db_session):
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

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = get_meeting(meeting_id=meeting.id)

    assert result.meeting_id == meeting.id
    assert result.already_summarised is False
    assert len(result.open_tasks) == 1


# ---------------------------------------------------------------------------
# save_meeting_summary
# ---------------------------------------------------------------------------

def test_save_meeting_summary_scrubs_and_persists(db_session):
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

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = save_meeting_summary(
            meeting_id=meeting.id,
            session_id=session.id,
            summary="patient 943 476 5919 was discussed",
        )

    assert result.note_id is not None

    saved = db_session.get(Note, result.note_id)
    assert "943 476 5919" not in saved.content
    assert "[NHS_ID_1]" in saved.content


def test_save_meeting_summary_tasks_linked_count(db_session):
    from wizard.tools import save_meeting_summary
    from wizard.models import WizardSession, Meeting, Task, MeetingTasks
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

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = save_meeting_summary(
            meeting_id=meeting.id,
            session_id=session.id,
            summary="sprint summary",
            task_ids=[task1.id, task2.id],
        )

    assert result.tasks_linked == 2


# ---------------------------------------------------------------------------
# session_end
# ---------------------------------------------------------------------------

def test_session_end_saves_summary_note(db_session):
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

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = session_end(
            session_id=session_id,
            summary="wrapped up today's work",
        )

    assert result.note_id is not None
    assert result.notion_write_back.ok is True

    saved = db_session.get(Note, result.note_id)
    assert saved.note_type == NoteType.SESSION_SUMMARY
    assert saved.session_id == session_id

    wb_mock.push_session_summary.assert_called_once()
    called_session = wb_mock.push_session_summary.call_args[0][0]
    assert called_session.daily_page_id == "test-daily-page"


def test_session_end_session_state_saved_true_on_happy_path(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus, SessionState

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    state = SessionState(
        intent="finish auth refactor",
        working_set=[1, 2],
        state_delta="Completed token refresh logic",
        open_loops=["rate limiting"],
        next_actions=["write tests"],
        closure_status="clean",
    )

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = session_end(
            session_id=session.id,
            summary="wrapped up",
            session_state=state,
        )

    assert result.session_state_saved is True


def test_session_end_session_state_saved_false_when_write_fails(db_session):
    from unittest.mock import patch as _patch
    from wizard.tools import session_end
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus, SessionState

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    state = SessionState(
        intent="test",
        working_set=[],
        state_delta="none",
        open_loops=[],
        next_actions=[],
        closure_status="clean",
    )

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        with _patch("wizard.schemas.SessionState.model_dump_json", side_effect=RuntimeError("disk full")):
            result = session_end(
                session_id=session.id,
                summary="wrapped up",
                session_state=state,
            )

    assert result.session_state_saved is False


# ---------------------------------------------------------------------------
# ingest_meeting
# ---------------------------------------------------------------------------

def test_ingest_meeting_creates_meeting(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import Meeting, MeetingCategory
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True, page_id="notion-meeting-page-id",
    )

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = ingest_meeting(
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


def test_ingest_meeting_dedup_by_source_id(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import Meeting
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True, page_id="notion-meeting-page-id",
    )

    existing = Meeting(title="Old", content="old", source_id="krisp-abc")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = ingest_meeting(title="New", content="new", source_id="krisp-abc")

    assert result.already_existed is True
    assert result.meeting_id == existing.id


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

def test_create_task_creates_and_links(db_session):
    from wizard.tools import create_task
    from wizard.models import Meeting, Task, TaskStatus, TaskPriority, MeetingTasks
    from wizard.schemas import WriteBackStatus
    from sqlmodel import select

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(
        ok=True, page_id="notion-task-page-id",
    )

    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    meeting_id = meeting.id

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        result = create_task(
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


def test_create_task_creates_paired_task_state(db_session):
    from wizard.tools import create_task
    from wizard.models import TaskState
    from wizard.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(ok=True)

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        response = create_task(name="new task")

    state = db_session.get(TaskState, response.task_id)
    assert state is not None
    assert state.note_count == 0
    assert state.decision_count == 0


# ---------------------------------------------------------------------------
# End-to-end compounding loop (design spec Section 10)
# ---------------------------------------------------------------------------

def test_compounding_loop_across_two_sessions(db_session):
    """Proves the full compounding context loop:
    session 1: session_start -> task_start -> save_note -> update_task_status -> session_end
    session 2: session_start -> task_start returns compounding=True with prior notes
    """
    from wizard.tools import (
        session_start, task_start, save_note,
        update_task_status, session_end,
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
        ok=False, error="Task has no notion_id",
    )
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)
    sync_mock = MagicMock()
    sync_mock.sync_all = MagicMock(return_value=[])

    patches, _, _ = _patch_tools(db_session, sync=sync_mock, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        # --- Session 1 ---
        s1 = session_start()
        session_id = s1.session_id

        # task_start -- no prior notes yet
        ts1 = task_start(task_id=task_id)
        assert ts1.compounding is False

        # save_note
        save_note(task_id=task_id, note_type=NoteType.INVESTIGATION, content="Found the root cause")

        # update_task_status
        update_task_status(task_id=task_id, new_status=TaskStatus.IN_PROGRESS)

        # session_end
        session_end(session_id=session_id, summary="Investigated auth bug")

        # --- Session 2 ---
        s2 = session_start()
        assert s2.session_id != session_id

        # task_start -- should see prior notes now
        ts2 = task_start(task_id=task_id)
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

def test_session_start_logs_tool_call(db_session):
    from wizard.tools import session_start
    from wizard.models import ToolCall
    from sqlmodel import select

    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools", **patches):
        result = session_start()

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "session_start"
    assert rows[0].session_id == result.session_id


def test_task_start_logs_tool_call_without_session_id(db_session):
    from wizard.tools import task_start
    from wizard.models import Task, ToolCall
    from sqlmodel import select

    task = Task(name="test", source_id="T-1", source_type="JIRA")
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        task_start(task_id=task.id)

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "task_start"
    assert rows[0].session_id is None


def test_session_end_logs_tool_call_with_session_id(db_session):
    from wizard.tools import session_end
    from wizard.models import WizardSession, ToolCall
    from sqlmodel import select

    session = WizardSession(daily_page_id="p-1")
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)
    assert session.id is not None

    patches, _, wb_mock = _patch_tools(db_session)
    from wizard.schemas import WriteBackStatus
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools", **patches):
        session_end(session_id=session.id, summary="done")

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "session_end"
    assert rows[0].session_id == session.id


def test_ingest_meeting_logs_tool_call_without_session_id(db_session):
    from wizard.tools import ingest_meeting
    from wizard.models import ToolCall
    from sqlmodel import select

    patches, _, wb_mock = _patch_tools(db_session)
    from wizard.schemas import WriteBackStatus
    wb_mock.push_meeting_to_notion = MagicMock(
        return_value=WriteBackStatus(ok=False, error="no token")
    )

    with patch.multiple("wizard.tools", **patches):
        ingest_meeting(title="standup", content="transcript here")

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "ingest_meeting"
    assert rows[0].session_id is None


def test_tool_call_sequence_within_session(db_session):
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

    patches, sync_mock, wb_mock = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])
    wb_mock.push_session_summary = MagicMock(
        return_value=WriteBackStatus(ok=True)
    )

    with patch.multiple("wizard.tools", **patches):
        s = session_start()
        save_note(
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="finding",
        )
        session_end(session_id=s.session_id, summary="wrap up")

    rows = db_session.exec(
        select(ToolCall).order_by(col(ToolCall.called_at))
    ).all()
    names = [r.tool_name for r in rows]
    assert names == ["session_start", "save_note", "session_end"]
    assert rows[0].session_id == s.session_id
    assert rows[1].session_id is None
    assert rows[2].session_id == s.session_id


# ---------------------------------------------------------------------------
# save_note — mental_model and TaskState wiring
# ---------------------------------------------------------------------------

def test_save_note_stores_mental_model_when_provided(db_session):
    from wizard.tools import save_note
    from wizard.models import Note, NoteType, Task

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        response = save_note(
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Race condition between token refresh and request",
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model == "Race condition between token refresh and request"
    assert response.mental_model_saved is True


def test_save_note_leaves_mental_model_null_when_not_provided(db_session):
    from wizard.tools import save_note
    from wizard.models import Note, NoteType, Task

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        response = save_note(
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="ref material",
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model is None
    assert response.mental_model_saved is False


def test_save_note_mental_model_saved_true_when_model_provided(db_session):
    from wizard.tools import save_note
    from wizard.models import NoteType, Task

    task = Task(name="t2")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = save_note(
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="some investigation",
            mental_model="State machine pattern",
        )

    assert result.mental_model_saved is True


def test_save_note_mental_model_saved_false_when_model_absent(db_session):
    from wizard.tools import save_note
    from wizard.models import NoteType, Task

    task = Task(name="t3")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = save_note(
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="some docs",
            mental_model=None,
        )

    assert result.mental_model_saved is False


def test_save_note_updates_task_state(db_session):
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

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        save_note(task_id=task.id, note_type=NoteType.DECISION, content="d")

    state = db_session.get(TaskState, task.id)
    db_session.refresh(state)
    assert state is not None
    assert state.note_count == 1
    assert state.decision_count == 1
    assert state.last_note_at is not None


# ---------------------------------------------------------------------------
# update_task_status — TaskState wiring
# ---------------------------------------------------------------------------

def test_update_task_status_records_last_status_change_at(db_session):
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

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        update_task_status(task_id=task.id, new_status=TaskStatus.IN_PROGRESS)

    state = db_session.get(TaskState, task.id)
    db_session.refresh(state)
    assert state is not None
    assert state.last_status_change_at is not None
    delta = _dt.datetime.now() - state.last_status_change_at
    assert delta.total_seconds() < 5


def test_update_task_status_does_not_reset_stale_days(db_session):
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

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("wizard.tools", **patches):
        update_task_status(task_id=task.id, new_status=TaskStatus.DONE)

    db_session.refresh(state)
    assert state.stale_days == 7
    assert state.note_count == 3


# ---------------------------------------------------------------------------
# rewind_task
# ---------------------------------------------------------------------------


def test_rewind_task_empty_timeline(db_session):
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskState, TaskStatus

    task = Task(name="empty task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    state = TaskState(
        task_id=task.id,
        last_touched_at=task.created_at,
        stale_days=0,
        note_count=0,
        decision_count=0,
    )
    db_session.add(state)
    db_session.commit()

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = rewind_task(task_id=task.id)

    assert result.timeline == []
    assert result.summary.total_notes == 0
    assert result.summary.duration_days == 0
    assert result.summary.last_activity == task.created_at
    assert result.task.id == task.id


def test_rewind_task_single_note(db_session):
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskState, TaskStatus, Note, NoteType

    task = Task(name="single note task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    state = TaskState(
        task_id=task.id,
        last_touched_at=task.created_at,
        stale_days=0,
        note_count=1,
        decision_count=0,
    )
    db_session.add(state)

    note = Note(
        note_type=NoteType.INVESTIGATION,
        content="some investigation note",
        task_id=task.id,
    )
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = rewind_task(task_id=task.id)

    assert result.summary.total_notes == 1
    assert result.summary.duration_days == 0
    assert result.summary.last_activity == note.created_at
    assert len(result.timeline) == 1
    assert result.timeline[0].note_id == note.id
    assert result.timeline[0].note_type == NoteType.INVESTIGATION


def test_rewind_task_multiple_notes_sort_order_and_preview(db_session):
    import datetime
    from wizard.tools import rewind_task
    from wizard.models import Task, TaskState, TaskStatus, Note, NoteType

    task = Task(name="multi note task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    state = TaskState(
        task_id=task.id,
        last_touched_at=task.created_at,
        stale_days=0,
        note_count=2,
        decision_count=0,
    )
    db_session.add(state)

    t_old = datetime.datetime(2025, 1, 1, 10, 0, 0)
    t_new = datetime.datetime(2025, 1, 6, 10, 0, 0)  # 5 days later

    old_note = Note(
        note_type=NoteType.INVESTIGATION,
        content="old note",
        task_id=task.id,
    )
    old_note.created_at = t_old
    db_session.add(old_note)

    long_content = "x" * 300
    new_note = Note(
        note_type=NoteType.DECISION,
        content=long_content,
        task_id=task.id,
    )
    new_note.created_at = t_new
    db_session.add(new_note)

    db_session.commit()
    db_session.refresh(old_note)
    db_session.refresh(new_note)

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        result = rewind_task(task_id=task.id)

    assert result.summary.total_notes == 2
    assert result.summary.duration_days == 5
    assert result.summary.last_activity == t_new

    # oldest first
    assert result.timeline[0].note_id == old_note.id
    assert result.timeline[1].note_id == new_note.id

    # preview truncated at 200 chars
    assert len(result.timeline[1].preview) == 200
    assert result.timeline[1].preview == long_content[:200]


def test_rewind_task_not_found_raises_tool_error(db_session):
    from fastmcp.exceptions import ToolError
    from wizard.tools import rewind_task

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError, match="Task 9999 not found"):
            rewind_task(task_id=9999)


def test_rewind_task_raises_tool_error_for_missing_task_state(db_session):
    from fastmcp.exceptions import ToolError
    from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus
    from wizard.tools import rewind_task

    task = Task(
        name="No State Task",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    # Deliberately do NOT create a TaskState row

    assert task.id is not None
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("wizard.tools", **patches):
        with pytest.raises(ToolError, match="TaskState missing for task"):
            rewind_task(task_id=task.id)
