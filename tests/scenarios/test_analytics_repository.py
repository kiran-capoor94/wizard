"""Behaviour tests for AnalyticsRepository — SQL GROUP BY aggregation."""

import datetime

from wizard.models import Note, NoteType, Task, WizardSession
from wizard.repositories.analytics import AnalyticsRepository


def _make_session(db, closed_by="hook") -> WizardSession:
    s = WizardSession(
        summary="s", closed_by=closed_by,
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    db.add(s)
    db.flush()
    db.refresh(s)
    return s


def _make_task(db, name="t") -> Task:
    t = Task(
        name=name, status="todo", priority="medium", category="issue",
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _make_note(db, task_id, session_id, note_type=NoteType.INVESTIGATION, mental_model=None):
    n = Note(
        note_type=note_type, content="c", task_id=task_id, session_id=session_id,
        mental_model=mental_model,
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    db.add(n)
    db.flush()
    return n


class TestNoteStats:
    def test_counts_by_type(self, db_session):
        today = datetime.date.today()
        s = _make_session(db_session)
        t = _make_task(db_session)
        _make_note(db_session, t.id, s.id, NoteType.INVESTIGATION)
        _make_note(db_session, t.id, s.id, NoteType.DECISION)
        _make_note(db_session, t.id, s.id, NoteType.DECISION)

        stats = AnalyticsRepository().get_note_stats(db_session, today, today)
        assert stats["by_type"]["investigation"] == 1
        assert stats["by_type"]["decision"] == 2
        assert stats["total"] == 3


class TestTaskStats:
    def test_worked_and_avg_notes(self, db_session):
        today = datetime.date.today()
        s = _make_session(db_session)
        t1 = _make_task(db_session, "t1")
        t2 = _make_task(db_session, "t2")
        _make_note(db_session, t1.id, s.id)
        _make_note(db_session, t1.id, s.id)
        _make_note(db_session, t2.id, s.id)

        stats = AnalyticsRepository().get_task_stats(db_session, today, today)
        assert stats["worked"] == 2
        assert stats["avg_notes_per_task"] == 1.5
