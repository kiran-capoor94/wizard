"""Scenario: NoteRepository.get_recent returns notes within the day window."""

import datetime

from wizard.models import Note, NoteType
from wizard.repositories.note import NoteRepository


class TestNoteGetRecent:
    def test_returns_notes_within_window(self, db_session):
        repo = NoteRepository()
        old = Note(
            note_type=NoteType.INVESTIGATION,
            content="old note",
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10),
            status="active",
        )
        recent = Note(
            note_type=NoteType.DECISION,
            content="recent note",
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3),
            status="active",
        )
        db_session.add(old)
        db_session.add(recent)
        db_session.flush()

        results = repo.get_recent(db_session, days=7)
        content_set = {n.content for n in results}
        assert "recent note" in content_set
        assert "old note" not in content_set

    def test_excludes_non_active_notes(self, db_session):
        repo = NoteRepository()
        superseded = Note(
            note_type=NoteType.INVESTIGATION,
            content="superseded note",
            created_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
            status="superseded",
        )
        db_session.add(superseded)
        db_session.flush()

        results = repo.get_recent(db_session, days=7)
        assert all(n.status == "active" for n in results)
