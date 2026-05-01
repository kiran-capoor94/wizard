"""Scenario tests for FTS5 search across notes, sessions, meetings, tasks."""

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from wizard.models import Meeting, Note, NoteType, Task, WizardSession
from wizard.repositories.search import SearchRepository


@pytest.fixture
def fts_engine():
    """In-memory SQLite engine with FTS5 tables created from scratch."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5("
            "content, note_type UNINDEXED,"
            "content='note', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5("
            "summary,"
            "content='wizardsession', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS meeting_fts USING fts5("
            "content, title,"
            "content='meeting', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS task_fts USING fts5("
            "name,"
            "content='task', content_rowid='id')"
        ))
        # Triggers for notes
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS note_fts_ai AFTER INSERT ON note BEGIN "
            "INSERT INTO note_fts(rowid, content, note_type) "
            "VALUES (new.id, new.content, new.note_type); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS meeting_fts_ai AFTER INSERT ON meeting BEGIN "
            "INSERT INTO meeting_fts(rowid, content, title) "
            "VALUES (new.id, new.content, new.title); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS task_fts_ai AFTER INSERT ON task BEGIN "
            "INSERT INTO task_fts(rowid, name) "
            "VALUES (new.id, new.name); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS session_fts_ai AFTER INSERT ON wizardsession BEGIN "
            "INSERT INTO session_fts(rowid, summary) "
            "VALUES (new.id, new.summary); END"
        ))
        conn.commit()
    return engine


@pytest.fixture
def fts_db(fts_engine):
    with Session(fts_engine) as session:
        yield session


class TestSearchRepository:
    def test_keyword_in_note_body_found(self, fts_db):
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="JWT decoder monkey-patch failed in auth flow",
        )
        fts_db.add(note)
        fts_db.flush()

        results = SearchRepository().search(fts_db, "monkey-patch", limit=10)
        assert len(results) == 1
        assert results[0].entity_type == "note"
        assert results[0].entity_id == note.id
        assert "monkey" in results[0].snippet.lower()

    def test_entity_type_filter_narrows_results(self, fts_db):
        note = Note(note_type=NoteType.DECISION, content="decided to use Redis caching")
        task = Task(name="implement Redis caching layer")
        fts_db.add(note)
        fts_db.add(task)
        fts_db.flush()

        all_results = SearchRepository().search(fts_db, "Redis", limit=10)
        note_results = SearchRepository().search(fts_db, "Redis", limit=10, entity_type="note")
        task_results = SearchRepository().search(fts_db, "Redis", limit=10, entity_type="task")

        assert len(all_results) == 2
        assert len(note_results) == 1
        assert note_results[0].entity_type == "note"
        assert len(task_results) == 1
        assert task_results[0].entity_type == "task"

    def test_meeting_title_and_content_searched(self, fts_db):
        meeting = Meeting(
            title="Sprint planning session",
            content="We discussed the Kafka migration timeline and blockers.",
        )
        fts_db.add(meeting)
        fts_db.flush()

        results = SearchRepository().search(fts_db, "Kafka", limit=10)
        assert len(results) == 1
        assert results[0].entity_type == "meeting"

    def test_session_summary_searched(self, fts_db):
        session = WizardSession(agent="claude-code", summary="Investigated Redis cache invalidation issue")
        fts_db.add(session)
        fts_db.flush()

        results = SearchRepository().search(fts_db, "Redis", limit=10, entity_type="session")
        assert len(results) == 1
        assert results[0].entity_type == "session"
        assert "Redis" in results[0].snippet or "redis" in results[0].snippet.lower()
