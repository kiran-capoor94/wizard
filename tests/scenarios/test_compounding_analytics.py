"""Scenario: compounding metric uses WizardSession.created_at as the prior-context boundary."""

import datetime

from sqlmodel import Session

from wizard.cli.analytics import query_compounding
from wizard.models import Note, NoteType, ToolCall, WizardSession


def test_compounding_counts_sessions_with_prior_notes(db_session: Session):
    now = datetime.datetime.now()
    start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    # Session 1: no notes existed before it started
    s1 = WizardSession(created_at=now)
    db_session.add(s1)
    db_session.flush()
    db_session.refresh(s1)
    db_session.add(Note(
        note_type=NoteType.INVESTIGATION,
        content="from session 1",
        session_id=s1.id,
        created_at=now + datetime.timedelta(minutes=5),
    ))
    db_session.add(ToolCall(
        session_id=s1.id,
        tool_name="task_start",
        called_at=now + datetime.timedelta(minutes=1),
    ))

    # Session 2: s1's note predates it → prior context exists
    s2 = WizardSession(created_at=now + datetime.timedelta(hours=1))
    db_session.add(s2)
    db_session.flush()
    db_session.refresh(s2)
    db_session.add(ToolCall(
        session_id=s2.id,
        tool_name="task_start",
        called_at=now + datetime.timedelta(hours=1, minutes=1),
    ))
    db_session.flush()

    result = query_compounding(db_session, start, end)

    # s1: no prior notes → not counted
    # s2: note from s1 predates s2.created_at → counted
    assert result == 0.5


def test_compounding_zero_with_no_task_starts(db_session: Session):
    now = datetime.datetime.now()
    start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    db_session.add(WizardSession(created_at=now))
    db_session.flush()
    # No task_start ToolCall

    assert query_compounding(db_session, start, end) == 0.0


def test_compounding_full_when_prior_note_predates_all_sessions(db_session: Session):
    now = datetime.datetime.now()
    start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    # Note created before both sessions
    db_session.add(Note(
        note_type=NoteType.DECISION,
        content="prior decision",
        created_at=now - datetime.timedelta(hours=2),
    ))

    for i in range(2):
        s = WizardSession(created_at=now + datetime.timedelta(hours=i))
        db_session.add(s)
        db_session.flush()
        db_session.refresh(s)
        db_session.add(ToolCall(
            session_id=s.id,
            tool_name="task_start",
            called_at=now + datetime.timedelta(hours=i, minutes=1),
        ))

    db_session.flush()

    assert query_compounding(db_session, start, end) == 1.0
