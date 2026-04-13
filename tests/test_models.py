import time

import pytest


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

from pydantic import ValidationError

from wizard.schemas import SessionState


class TestSessionState:
    def test_round_trip_with_all_six_fields(self):
        data = {
            "intent": "Progress ADRs to decision",
            "working_set": [40, 39],
            "state_delta": "ADR 005 accepted. ADR 007 reframed.",
            "open_loops": ["ADR changes not committed"],
            "next_actions": ["Commit ADR 005 + 007"],
            "closure_status": "interrupted",
        }
        state = SessionState.model_validate(data)
        assert state.intent == data["intent"]
        assert state.working_set == [40, 39]
        assert state.closure_status == "interrupted"
        assert state.model_dump() == data

    def test_default_lists_are_empty(self):
        state = SessionState.model_validate(
            {"intent": "x", "state_delta": "y", "closure_status": "clean"}
        )
        assert state.working_set == []
        assert state.open_loops == []
        assert state.next_actions == []

    def test_closure_status_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            SessionState.model_validate(
                {"intent": "x", "state_delta": "y", "closure_status": "paused"}
            )

    def test_intent_required(self):
        with pytest.raises(ValidationError):
            SessionState.model_validate(
                {"state_delta": "y", "closure_status": "clean"}
            )
