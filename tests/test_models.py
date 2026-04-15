import time

import pytest


def test_timestamp_mixin_created_at_is_always_naive():
    """TimestampMixin.created_at must never carry timezone info.

    pydantic v2 with validate_default=True converts datetime.now() to
    UTC-aware. SQLite strips timezone on round-trip. This mismatch causes
    TypeError when repositories subtract UTC-aware from naive datetimes.
    All timestamps must be consistently naive.
    """
    from wizard.models import Task
    task = Task(name="tz check")
    assert task.created_at.tzinfo is None, (
        f"created_at should be naive but got tzinfo={task.created_at.tzinfo}"
    )


def test_timestamp_mixin_updated_at_is_always_naive():
    from wizard.models import Task
    task = Task(name="tz check")
    assert task.updated_at.tzinfo is None


def test_created_at_is_not_frozen_at_module_load(db_session):
    from wizard.models import Task

    t1 = Task(name="first")
    db_session.add(t1)
    db_session.commit()
    db_session.refresh(t1)

    time.sleep(0.05)

    t2 = Task(name="second")
    db_session.add(t2)
    db_session.commit()
    db_session.refresh(t2)

    assert t1.created_at != t2.created_at


def test_task_has_updated_at_field(db_session):
    from wizard.models import Task

    task = Task(name="foo")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.updated_at is not None


def test_updated_at_changes_on_update(db_session):
    from wizard.models import Task

    task = Task(name="foo")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    original_updated_at = task.updated_at

    time.sleep(0.05)

    task.name = "bar"
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.updated_at > original_updated_at


def test_task_can_be_created_without_due_date(db_session):
    from wizard.models import Task

    task = Task(name="no deadline")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.due_date is None


def test_meeting_tasks_relationship(db_session):
    from wizard.models import Meeting, MeetingTasks, Task

    meeting = Meeting(title="standup", content="standup notes")
    task = Task(name="action item")
    db_session.add(meeting)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(meeting)
    db_session.refresh(task)
    assert meeting.id is not None
    assert task.id is not None

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(meeting)

    assert len(meeting.tasks) == 1
    assert meeting.tasks[0].id == task.id


def test_task_meetings_relationship(db_session):
    from wizard.models import Meeting, MeetingTasks, Task

    meeting = Meeting(title="planning", content="planning notes")
    task = Task(name="action item")
    db_session.add(meeting)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(meeting)
    db_session.refresh(task)
    assert meeting.id is not None
    assert task.id is not None

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()
    db_session.refresh(task)

    assert len(task.meetings) == 1
    assert task.meetings[0].id == meeting.id


def test_invalid_enum_value_rejected():
    from pydantic import ValidationError

    from wizard.models import Task

    with pytest.raises(ValidationError):
        Task(name="test", priority="invalid_value")  # pyright: ignore[reportArgumentType]


def test_task_has_notion_id(db_session):
    from wizard.models import Task
    task = Task(name="test")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.notion_id is None


def test_meeting_has_title_and_notion_id(db_session):
    from wizard.models import Meeting
    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    assert meeting.title == "standup"
    assert meeting.notion_id is None


def test_note_has_meeting_id(db_session):
    from wizard.models import Note, NoteType
    note = Note(note_type=NoteType.INVESTIGATION, content="investigating")
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    assert note.meeting_id is None


def test_note_has_session_summary_type(db_session):
    from wizard.models import Note, NoteType, WizardSession
    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    note = Note(note_type=NoteType.SESSION_SUMMARY, content="session wrap", session_id=session.id)
    db_session.add(note)
    db_session.commit()
    db_session.refresh(note)
    assert note.note_type == NoteType.SESSION_SUMMARY


def test_wizard_session_table_name(db_session):
    from sqlalchemy import inspect
    from wizard.database import engine
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "wizardsession" in tables
    assert "wizardsessions" not in tables


def test_meeting_category_has_general(db_session):
    from wizard.models import Meeting, MeetingCategory
    meeting = Meeting(title="misc", content="...", category=MeetingCategory.GENERAL)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    assert meeting.category == MeetingCategory.GENERAL


# --- Task 1: SessionState schema ---


class TestSessionState:
    def test_round_trip_with_all_six_fields(self):
        from wizard.schemas import SessionState

        data = {
            "intent": "Progress ADRs to decision",
            "working_set": [40, 39],
            "state_delta": "ADR 005 accepted. ADR 007 reframed.",
            "open_loops": ["ADR changes not committed"],
            "next_actions": ["Commit ADR 005 + 007"],
            "closure_status": "interrupted",
            "tool_registry": None,
        }
        state = SessionState.model_validate(data)
        assert state.intent == data["intent"]
        assert state.working_set == [40, 39]
        assert state.closure_status == "interrupted"
        assert state.model_dump() == data

    def test_default_lists_are_empty(self):
        from wizard.schemas import SessionState

        state = SessionState.model_validate(
            {"intent": "x", "state_delta": "y", "closure_status": "clean"}
        )
        assert state.working_set == []
        assert state.open_loops == []
        assert state.next_actions == []

    def test_closure_status_rejects_unknown_value(self):
        from pydantic import ValidationError

        from wizard.schemas import SessionState

        with pytest.raises(ValidationError):
            SessionState.model_validate(
                {"intent": "x", "state_delta": "y", "closure_status": "paused"}
            )

    def test_intent_required(self):
        from pydantic import ValidationError

        from wizard.schemas import SessionState

        with pytest.raises(ValidationError):
            SessionState.model_validate(
                {"state_delta": "y", "closure_status": "clean"}
            )


# --- Task 2: Note.mental_model ---


class TestNoteMentalModel:
    def test_note_can_store_mental_model(self, db_session):
        from wizard.models import Note, NoteType

        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Auth fails due to a token-refresh race condition",
        )
        db_session.add(note)
        db_session.flush()
        db_session.refresh(note)
        assert note.mental_model == "Auth fails due to a token-refresh race condition"

    def test_mental_model_defaults_to_none(self, db_session):
        from wizard.models import Note, NoteType

        note = Note(note_type=NoteType.DOCS, content="x")
        db_session.add(note)
        db_session.flush()
        db_session.refresh(note)
        assert note.mental_model is None


# --- Task 3: WizardSession.session_state ---


class TestWizardSessionState:
    def test_session_state_defaults_to_none(self, db_session):
        from wizard.models import WizardSession

        session = WizardSession()
        db_session.add(session)
        db_session.flush()
        db_session.refresh(session)
        assert session.session_state is None

    def test_session_state_round_trips_json(self, db_session):
        from wizard.models import WizardSession
        from wizard.schemas import SessionState

        state = SessionState(
            intent="x",
            state_delta="y",
            closure_status="clean",
        )
        session = WizardSession(session_state=state.model_dump_json())
        db_session.add(session)
        db_session.flush()
        db_session.refresh(session)
        assert session.session_state is not None
        loaded = SessionState.model_validate_json(session.session_state)
        assert loaded == state


# --- Task 4: TaskState model ---

import datetime as _dt


class TestTaskStateModel:
    def test_task_state_defaults(self, db_session):
        from wizard.models import Task, TaskState

        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        state = TaskState(
            task_id=task.id,
            last_touched_at=task.created_at,
        )
        db_session.add(state)
        db_session.flush()
        db_session.refresh(state)

        assert state.task_id == task.id
        assert state.note_count == 0
        assert state.decision_count == 0
        assert state.last_note_at is None
        assert state.last_status_change_at is None
        assert state.last_touched_at == task.created_at
        assert state.stale_days == 0

    def test_task_state_table_name_is_snake_case(self):
        from wizard.models import TaskState

        # __tablename__ is a SQLAlchemy declared_attr at the type level but a
        # plain string at runtime; cast for the assertion.
        assert str(TaskState.__tablename__) == "task_state"

    def test_task_state_can_store_all_fields(self, db_session):
        from wizard.models import Task, TaskState

        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        now = _dt.datetime.now()
        state = TaskState(
            task_id=task.id,
            note_count=4,
            decision_count=1,
            last_note_at=now,
            last_status_change_at=now,
            last_touched_at=now,
            stale_days=2,
        )
        db_session.add(state)
        db_session.flush()
        db_session.refresh(state)
        assert state.note_count == 4
        assert state.decision_count == 1
        assert state.last_note_at == now
        assert state.stale_days == 2


def test_toolcall_called_at_is_naive():
    """ToolCall.called_at default must be timezone-naive (consistent with SQLite storage)."""
    from wizard.models import ToolCall
    tc = ToolCall(tool_name="test_tool")
    assert tc.called_at.tzinfo is None
