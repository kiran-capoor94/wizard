from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# task_start
# ---------------------------------------------------------------------------


async def test_task_start_returns_compounding_true_when_prior_notes(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.repositories import NoteRepository, TaskRepository
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
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.compounding is True
    assert len(result.prior_notes) == 1


async def test_task_start_returns_compounding_false_when_no_notes(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    task = Task(name="new task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.compounding is False


async def test_task_start_raises_when_task_not_found(db_session):
    from fastmcp.exceptions import ToolError

    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        with pytest.raises(ToolError, match="Task 999 not found"):
            await task_start(ctx, task_id=999, t_repo=TaskRepository(), n_repo=NoteRepository())


async def test_task_start_latest_mental_model_returns_newest_note_model(db_session):
    import datetime

    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

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
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.latest_mental_model == "State machine"


async def test_task_start_latest_mental_model_none_when_no_notes_have_model(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository
    from wizard.tools import task_start

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
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert result.latest_mental_model is None


async def test_task_start_returns_prior_notes_oldest_first(db_session):
    """prior_notes must be ordered oldest-first (matching rewind_task convention)."""
    import datetime

    from wizard.models import (
        Note,
        NoteType,
        Task,
        TaskCategory,
        TaskPriority,
        TaskState,
        TaskStatus,
    )
    from wizard.tools import task_start

    task = Task(
        name="Fix auth",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    state = TaskState(
        task_id=task.id,
        note_count=2,
        decision_count=0,
        last_touched_at=datetime.datetime.now(),
        stale_days=0,
    )
    db_session.add(state)

    older = Note(
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="older note",
        created_at=datetime.datetime(2026, 1, 1, 10, 0, 0),
    )
    newer = Note(
        task_id=task.id,
        note_type=NoteType.DECISION,
        content="newer note",
        created_at=datetime.datetime(2026, 1, 3, 10, 0, 0),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        result = await task_start(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    assert len(result.prior_notes) == 2
    assert result.prior_notes[0].content == "older note"
    assert result.prior_notes[1].content == "newer note"


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------


async def test_save_note_scrubs_and_persists(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
    from wizard.security import SecurityService
    from wizard.tools import save_note

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="john@example.com found a bug",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.note_id is not None

    saved_note = db_session.get(Note, result.note_id)
    assert "john@example.com" not in saved_note.content
    assert "[EMAIL_1]" in saved_note.content


async def test_save_note_stores_mental_model_when_provided(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        response = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Race condition between token refresh and request",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model == "Race condition between token refresh and request"
    assert response.mental_model_saved is True


async def test_save_note_leaves_mental_model_null_when_not_provided(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        response = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="ref material",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model is None
    assert response.mental_model_saved is False


async def test_save_note_mental_model_saved_true_when_model_provided(db_session):
    from wizard.models import NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t2")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="some investigation",
            mental_model="State machine pattern",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.mental_model_saved is True


async def test_save_note_mental_model_saved_false_when_model_absent(db_session):
    from wizard.models import NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t3")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="some docs",
            mental_model=None,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.mental_model_saved is False


async def test_save_note_updates_task_state(db_session):
    from wizard.models import NoteType, Task, TaskState
    from wizard.repositories import TaskStateRepository as _TaskStateRepo
    from wizard.tools import save_note

    def task_state_repo():
        return _TaskStateRepo()

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    # Pre-create the TaskState row so we can refresh it from the same session.
    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DECISION,
            content="d",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    state = db_session.get(TaskState, task.id)
    db_session.refresh(state)
    assert state is not None
    assert state.note_count == 1
    assert state.decision_count == 1
    assert state.last_note_at is not None


async def test_save_note_uses_session_id_from_ctx_state_when_set(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    await ctx.set_state("current_session_id", 42)

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="content",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.session_id == 42


async def test_save_note_session_id_null_when_no_ctx_state(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()  # no set_state called

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="content",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.session_id is None


# --- elicitation: save_note ---


async def test_save_note_elicits_mental_model_for_investigation(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="I now understand the root cause is X")

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="looked at logs",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "I now understand the root cause is X"


async def test_save_note_elicits_mental_model_for_decision(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="We chose approach B for simplicity")

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DECISION,
            content="chose B",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "We chose approach B for simplicity"


async def test_save_note_does_not_elicit_for_docs_notes(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="should not be used")

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="docs",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    # DOCS note: elicit should NOT have been called, mental_model stays None
    assert note.mental_model is None


async def test_save_note_mental_model_param_skips_elicitation(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="this should not win")

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
            mental_model="caller provided this",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "caller provided this"


async def test_save_note_handles_elicit_failure_gracefully(db_session):
    from wizard.models import NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(supports_elicit=False)

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.note_id is not None  # tool succeeded despite elicit failure


async def test_save_note_scrubs_mental_model_when_passed_directly(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Spoke with john@example.com about the issue",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note is not None
    assert "john@example.com" not in note.mental_model
    assert "[EMAIL_1]" in note.mental_model


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


async def test_create_task_creates_and_links(db_session):
    from sqlmodel import select

    from wizard.models import Meeting, MeetingTasks, Task, TaskPriority, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import create_task

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
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskStateRepository
        from wizard.security import SecurityService
        result = await create_task(
            ctx,
            name="Fix john@example.com auth bug",
            priority=TaskPriority.HIGH,
            meeting_id=meeting_id,
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
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
    from wizard.models import TaskState
    from wizard.schemas import WriteBackStatus
    from wizard.tools import create_task

    wb_mock = MagicMock()
    wb_mock.push_task_to_notion.return_value = WriteBackStatus(ok=True)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskStateRepository
        from wizard.security import SecurityService
        response = await create_task(
            ctx,
            name="new task",
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    state = db_session.get(TaskState, response.task_id)
    assert state is not None
    assert state.note_count == 0
    assert state.decision_count == 0


async def test_create_task_links_tool_call_to_active_session(db_session):
    from sqlmodel import select

    from wizard.models import ToolCall, WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import create_task

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
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskStateRepository
        from wizard.security import SecurityService
        await create_task(
            ctx,
            name="new task",
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    rows = list(db_session.execute(select(ToolCall)).scalars().all())
    assert len(rows) == 1
    assert rows[0].session_id == session.id


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------


async def test_update_task_updates_single_field(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_due_date.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            due_date="2026-04-17T14:00:00Z",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.task_id == task.id
    assert "due_date" in result.updated_fields
    assert len(result.updated_fields) == 1

    db_session.refresh(task)
    assert task.due_date is not None


async def test_update_task_updates_multiple_fields(db_session):
    from wizard.models import Task, TaskPriority, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_priority.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert set(result.updated_fields) == {"status", "priority"}
    assert result.task_state_updated is True

    db_session.refresh(task)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.priority == TaskPriority.HIGH


async def test_update_task_raises_when_no_fields(db_session):
    from fastmcp.exceptions import ToolError

    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        with pytest.raises(ToolError, match="At least one field"):
            await update_task(
                ctx,
                task_id=task.id,
                t_repo=TaskRepository(),
                sec=SecurityService(),
                t_state_repo=TaskStateRepository(),
                wb=MagicMock(),
            )


async def test_update_task_done_elicits_outcome(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    task = Task(name="test", status=TaskStatus.IN_PROGRESS, notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)
    wb_mock.append_task_outcome.return_value = WriteBackStatus(ok=True)

    ctx = MockContext(elicit_response="Completed successfully")
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.DONE,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    wb_mock.append_task_outcome.assert_called_once()


async def test_update_task_done_without_notion_id_skips_elicit(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    task = Task(name="test", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    wb_mock = MagicMock()
    wb_mock.push_task_status.return_value = WriteBackStatus(ok=True)
    wb_mock.push_task_status_to_notion.return_value = WriteBackStatus(ok=True)

    ctx = MockContext(elicit_response="should not be used")
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.DONE,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    wb_mock.append_task_outcome.assert_not_called()


async def test_update_task_invalid_due_date_format(db_session):
    from fastmcp.exceptions import ToolError

    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        with pytest.raises(ToolError, match="Invalid due_date format"):
            await update_task(
                ctx,
                task_id=task.id,
                due_date="not-a-date",
                t_repo=TaskRepository(),
                sec=SecurityService(),
                t_state_repo=TaskStateRepository(),
                wb=MagicMock(),
            )


async def test_update_task_name_is_scrubbed(db_session):
    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await update_task(
            ctx,
            task_id=task.id,
            name="john@example.com reported bug",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=MagicMock(),
        )

    db_session.refresh(task)
    assert "john@example.com" not in task.name
    assert "[EMAIL_1]" in task.name


async def test_update_task_due_date_writeback(db_session):
    from wizard.models import Task
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_due_date.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            due_date="2026-04-17T14:00:00Z",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.due_date_writeback is not None
    assert result.due_date_writeback.ok is True
    wb_mock.push_task_due_date.assert_called_once()


async def test_update_task_priority_writeback(db_session):
    from wizard.models import Task, TaskPriority
    from wizard.schemas import WriteBackStatus
    from wizard.tools import update_task

    wb_mock = MagicMock()
    wb_mock.push_task_priority.return_value = WriteBackStatus(ok=True)

    task = Task(name="test", notion_id="notion-123")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            priority=TaskPriority.HIGH,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    assert result.priority_writeback is not None
    assert result.priority_writeback.ok is True
    wb_mock.push_task_priority.assert_called_once()


async def test_update_task_notion_id(db_session):
    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            notion_id="notion-456",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=MagicMock(),
        )

    assert "notion_id" in result.updated_fields
    db_session.refresh(task)
    assert task.notion_id == "notion-456"


async def test_update_task_source_url(db_session):
    from wizard.models import Task
    from wizard.tools import update_task

    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            source_url="https://github.com/org/repo/issues/123",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=MagicMock(),
        )

    assert "source_url" in result.updated_fields
    db_session.refresh(task)
    assert task.source_url == "https://github.com/org/repo/issues/123"


async def test_update_task_outcome_writeback_called_when_elicited(db_session):
    """Outcome writeback must be called when elicitation returns text."""
    import datetime

    from wizard.models import Task, TaskCategory, TaskPriority, TaskState, TaskStatus
    from wizard.tools import update_task

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

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await update_task(
            ctx,
            task_id=task.id,
            status=TaskStatus.DONE,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            t_state_repo=TaskStateRepository(),
            wb=wb_mock,
        )

    wb_mock.append_task_outcome.assert_called_once()
    call_args = wb_mock.append_task_outcome.call_args
    assert "Shipped the fix." in call_args[0][1]
    assert result.updated_fields == ["status"]


# ---------------------------------------------------------------------------
# rewind_task
# ---------------------------------------------------------------------------


async def test_rewind_task_empty_timeline(db_session):
    from wizard.models import Task, TaskStatus
    from wizard.repositories import TaskStateRepository as _TaskStateRepo
    from wizard.tools import rewind_task

    def task_state_repo():
        return _TaskStateRepo()

    task = Task(name="empty task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository
        result = await rewind_task(ctx, task_id=task.id, n_repo=NoteRepository())

    assert result.timeline == []
    assert result.summary.total_notes == 0
    assert result.summary.duration_days == 0


async def test_rewind_task_links_tool_call_to_session(db_session):
    from wizard.models import Task, TaskStatus, ToolCall
    from wizard.repositories import TaskStateRepository as _TaskStateRepo
    from wizard.tools import rewind_task

    def task_state_repo():
        return _TaskStateRepo()
    from sqlmodel import select

    task = Task(name="linked task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_state_repo().create_for_task(db_session, task)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = 99
    ctx = mock_ctx(impl)

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository
        await rewind_task(ctx, task_id=task.id, n_repo=NoteRepository())

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "rewind_task"
    assert rows[0].session_id == 99


# ---------------------------------------------------------------------------
# what_am_i_missing
# ---------------------------------------------------------------------------


async def test_what_am_i_missing_links_tool_call_to_session(db_session):
    from wizard.models import Task, TaskStatus, ToolCall
    from wizard.repositories import TaskStateRepository as _TaskStateRepo
    from wizard.tools import what_am_i_missing

    def task_state_repo():
        return _TaskStateRepo()
    from sqlmodel import select

    task = Task(name="gap task", status=TaskStatus.TODO)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    task_state_repo().create_for_task(db_session, task)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = 77
    ctx = mock_ctx(impl)

    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        await what_am_i_missing(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    rows = db_session.exec(select(ToolCall)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "what_am_i_missing"
    assert rows[0].session_id == 77


async def test_what_am_i_missing_stale_2_days_fires_lost_context_not_stale(db_session):
    """stale_days=2 with notes → lost_context fires; stale must NOT fire (threshold is >= 3)."""
    import datetime

    from wizard.models import (
        Note,
        NoteType,
        Task,
        TaskCategory,
        TaskPriority,
        TaskState,
        TaskStatus,
    )
    from wizard.tools import what_am_i_missing

    task = Task(name="T", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="some work")
    db_session.add(note)
    db_session.flush()
    db_session.refresh(note)

    last_note = datetime.datetime.now() - datetime.timedelta(days=2)
    state = TaskState(
        task_id=task.id,
        note_count=1,
        decision_count=0,
        last_note_at=last_note,
        last_touched_at=last_note,
        stale_days=2,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        result = await what_am_i_missing(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    signal_types = [s.type for s in result.signals]
    assert "lost_context" in signal_types
    assert "stale" not in signal_types


async def test_what_am_i_missing_stale_3_days_fires_stale_not_lost_context(db_session):
    """stale_days=3 with notes → stale fires; lost_context must NOT fire (no double-signal)."""
    import datetime

    from wizard.models import (
        Note,
        NoteType,
        Task,
        TaskCategory,
        TaskPriority,
        TaskState,
        TaskStatus,
    )
    from wizard.tools import what_am_i_missing

    task = Task(name="T", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    note = Note(task_id=task.id, note_type=NoteType.INVESTIGATION, content="some work")
    db_session.add(note)
    db_session.flush()
    db_session.refresh(note)

    last_note = datetime.datetime.now() - datetime.timedelta(days=3)
    state = TaskState(
        task_id=task.id,
        note_count=1,
        decision_count=0,
        last_note_at=last_note,
        last_touched_at=last_note,
        stale_days=3,
    )
    db_session.add(state)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools._helpers", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository
        result = await what_am_i_missing(ctx, task_id=task.id, t_repo=TaskRepository(), n_repo=NoteRepository())

    signal_types = [s.type for s in result.signals]
    assert "stale" in signal_types
    assert "lost_context" not in signal_types
