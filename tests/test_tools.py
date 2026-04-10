from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


def _mock_context():
    """Create a mock Context for testing tools that accept ctx parameter."""
    ctx = MagicMock()
    ctx.info = MagicMock()
    ctx.warning = MagicMock()
    ctx.report_progress = MagicMock()
    return ctx


def _mock_session(db_session):
    """Context manager that yields the test db_session instead of creating a new one."""
    @contextmanager
    def _inner():
        yield db_session
        db_session.flush()
    return _inner


def _patch_tools(db_session, sync=None, wb=None):
    """Patch tools module dependencies with test doubles. Returns (patches, sync_mock, wb_mock)."""
    sync_mock = sync or MagicMock()
    wb_mock = wb or MagicMock()

    patches = {
        "get_session": _mock_session(db_session),
        "sync_service": lambda: sync_mock,
        "writeback": lambda: wb_mock,
    }
    return patches, sync_mock, wb_mock


# ---------------------------------------------------------------------------
# session_start
# ---------------------------------------------------------------------------

def test_session_start_creates_session(db_session):
    from src.tools import session_start
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("src.tools", **patches):
        result = session_start(ctx=_mock_context())

    assert result.session_id is not None
    assert result.open_tasks is not None
    assert result.blocked_tasks is not None
    assert result.unsummarised_meetings is not None
    assert result.sync_results is not None


def test_session_start_calls_sync(db_session):
    from src.tools import session_start
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("src.tools", **patches):
        session_start(ctx=_mock_context())

    sync_mock.sync_all.assert_called_once()


def test_session_start_surfaces_sync_errors(db_session):
    from src.tools import session_start
    from src.schemas import SourceSyncStatus
    patches, sync_mock, _ = _patch_tools(db_session)
    sync_mock.sync_all = MagicMock(return_value=[
        SourceSyncStatus(source="jira", ok=False, error="Jira token not configured"),
        SourceSyncStatus(source="notion_tasks", ok=True),
        SourceSyncStatus(source="notion_meetings", ok=True),
    ])

    with patch.multiple("src.tools", **patches):
        result = session_start(ctx=_mock_context())

    assert len(result.sync_results) == 3
    jira_sync = result.sync_results[0]
    assert jira_sync.source == "jira"
    assert jira_sync.ok is False
    assert jira_sync.error == "Jira token not configured"
    assert result.sync_results[1].ok is True


# ---------------------------------------------------------------------------
# task_start
# ---------------------------------------------------------------------------

def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from src.models import Task, TaskStatus, Note, NoteType
    from src.tools import task_start

    task = Task(name="fix auth", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    note = Note(note_type=NoteType.INVESTIGATION, content="prior investigation", task_id=task.id)
    db_session.add(note)
    db_session.commit()

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("src.tools", **patches):
        result = task_start(task_id=task.id)

    assert result.compounding is True
    assert len(result.prior_notes) == 1


def test_task_start_returns_compounding_false_when_no_notes(db_session):
    from src.models import Task, TaskStatus
    from src.tools import task_start

    task = Task(name="new task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("src.tools", **patches):
        result = task_start(task_id=task.id)

    assert result.compounding is False


def test_task_start_raises_when_task_not_found(db_session):
    from src.tools import task_start
    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("src.tools", **patches):
        with pytest.raises(ValueError, match="Task 999 not found"):
            task_start(task_id=999)


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------

def test_save_note_scrubs_and_persists(db_session):
    from src.tools import save_note
    from src.models import Task, Note, NoteType

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session)
    with patch.multiple("src.tools", **patches):
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
    from src.tools import update_task_status
    from src.models import Task, TaskStatus
    from src.schemas import WriteBackStatus

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
    with patch.multiple("src.tools", **patches):
        result = update_task_status(task_id=task_id, new_status=TaskStatus.DONE)

    assert result.new_status == TaskStatus.DONE
    assert result.jira_write_back.ok is True
    assert result.notion_write_back.ok is False
    assert result.notion_write_back.error == "Task has no notion_id"

    task_fresh = db_session.get(Task, task_id)
    assert task_fresh.status == TaskStatus.DONE


def test_update_task_status_dual_writeback(db_session):
    from src.tools import update_task_status
    from src.models import Task, TaskStatus
    from src.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    task = Task(name="fix", source_id="ENG-1", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("src.tools", **patches):
        result = update_task_status(task_id=task.id, new_status=TaskStatus.DONE)

    assert result.jira_write_back.ok is True
    assert result.notion_write_back.ok is True


# ---------------------------------------------------------------------------
# get_meeting
# ---------------------------------------------------------------------------

def test_get_meeting_returns_content_and_open_tasks(db_session):
    from src.tools import get_meeting
    from src.models import Task, TaskStatus, Meeting, MeetingTasks

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
    with patch.multiple("src.tools", **patches):
        result = get_meeting(meeting_id=meeting.id)

    assert result.meeting_id == meeting.id
    assert result.already_summarised is False
    assert len(result.open_tasks) == 1


# ---------------------------------------------------------------------------
# save_meeting_summary
# ---------------------------------------------------------------------------

def test_save_meeting_summary_scrubs_and_persists(db_session):
    from src.tools import save_meeting_summary
    from src.models import WizardSession, Meeting, Note
    from src.schemas import WriteBackStatus

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
    with patch.multiple("src.tools", **patches):
        result = save_meeting_summary(
            meeting_id=meeting.id,
            session_id=session.id,
            summary="patient 943 476 5919 was discussed",
        )

    assert result.note_id is not None

    saved = db_session.get(Note, result.note_id)
    assert "943 476 5919" not in saved.content
    assert "[NHS_ID_1]" in saved.content


# ---------------------------------------------------------------------------
# session_end
# ---------------------------------------------------------------------------

def test_session_end_saves_summary_note(db_session):
    from src.tools import session_end
    from src.models import WizardSession, Note, NoteType
    from src.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None
    session_id = session.id

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("src.tools", **patches):
        result = session_end(
            session_id=session_id,
            summary="wrapped up today's work",
            ctx=_mock_context(),
        )

    assert result.note_id is not None

    saved = db_session.get(Note, result.note_id)
    assert saved.note_type == NoteType.SESSION_SUMMARY
    assert saved.session_id == session_id


# ---------------------------------------------------------------------------
# ingest_meeting
# ---------------------------------------------------------------------------

def test_ingest_meeting_creates_meeting(db_session):
    from src.tools import ingest_meeting
    from src.models import Meeting, MeetingCategory
    from src.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True, page_id="notion-meeting-page-id",
    )

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("src.tools", **patches):
        result = ingest_meeting(
            title="Sprint Planning",
            content="john@example.com reported a bug",
            source_id="krisp-abc",
            source_url="https://krisp.ai/m/abc",
            category=MeetingCategory.PLANNING,
            ctx=_mock_context(),
        )

    assert result.meeting_id is not None
    assert result.already_existed is False
    meeting = db_session.get(Meeting, result.meeting_id)
    assert "john@example.com" not in meeting.content
    assert "[EMAIL_1]" in meeting.content


def test_ingest_meeting_dedup_by_source_id(db_session):
    from src.tools import ingest_meeting
    from src.models import Meeting
    from src.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True, page_id="notion-meeting-page-id",
    )

    existing = Meeting(title="Old", content="old", source_id="krisp-abc")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    patches, _, _ = _patch_tools(db_session, wb=wb_mock)
    with patch.multiple("src.tools", **patches):
        result = ingest_meeting(title="New", content="new", source_id="krisp-abc", ctx=_mock_context())

    assert result.already_existed is True
    assert result.meeting_id == existing.id


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

def test_create_task_creates_and_links(db_session):
    from src.tools import create_task
    from src.models import Meeting, Task, TaskStatus, TaskPriority, MeetingTasks
    from src.schemas import WriteBackStatus
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
    with patch.multiple("src.tools", **patches):
        result = create_task(
            name="Fix john@example.com auth bug",
            priority=TaskPriority.HIGH,
            meeting_id=meeting_id,
            ctx=_mock_context(),
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


# ---------------------------------------------------------------------------
# End-to-end compounding loop (design spec Section 10)
# ---------------------------------------------------------------------------

def test_compounding_loop_across_two_sessions(db_session):
    """Proves the full compounding context loop:
    session 1: session_start -> task_start -> save_note -> update_task_status -> session_end
    session 2: session_start -> task_start returns compounding=True with prior notes
    """
    from src.tools import (
        session_start, task_start, save_note,
        update_task_status, session_end,
    )
    from src.models import Task, TaskStatus, NoteType

    # Seed a task (simulating what sync would produce)
    task = Task(name="Fix auth", source_id="ENG-100", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None
    task_id: int = task.id

    from src.schemas import WriteBackStatus

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(
        ok=False, error="Task has no notion_id",
    )
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)
    sync_mock = MagicMock()
    sync_mock.sync_all = MagicMock(return_value=[])

    patches, _, _ = _patch_tools(db_session, sync=sync_mock, wb=wb_mock)
    with patch.multiple("src.tools", **patches):
        # --- Session 1 ---
        s1 = session_start(ctx=_mock_context())
        session_id = s1.session_id

        # task_start -- no prior notes yet
        ts1 = task_start(task_id=task_id)
        assert ts1.compounding is False

        # save_note
        save_note(task_id=task_id, note_type=NoteType.INVESTIGATION, content="Found the root cause")

        # update_task_status
        update_task_status(task_id=task_id, new_status=TaskStatus.IN_PROGRESS)

        # session_end
        session_end(session_id=session_id, summary="Investigated auth bug", ctx=_mock_context())

        # --- Session 2 ---
        s2 = session_start(ctx=_mock_context())
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
    from src.schemas import SessionStartResponse, SourceSyncStatus

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
