"""Behaviour tests for the recall-engine rewrite of SearchRepository."""
from wizard.repositories.search import _build_fts_query, _rrf_fuse


def test_build_fts_query_ors_prefix_terms():
    assert _build_fts_query("redis caching decision") == '"redis"* OR "caching"* OR "decision"*'


def test_build_fts_query_splits_on_punctuation():
    assert _build_fts_query("monkey-patch auth!") == '"monkey"* OR "patch"* OR "auth"*'


def test_build_fts_query_empty_when_no_word_chars():
    assert _build_fts_query("   ") == ""
    assert _build_fts_query("!!! ??? ") == ""


def test_rrf_fuse_rewards_agreement_across_lanes():
    # ("note", 1) is rank-0 in both lanes; ("note", 2) is rank-0 in one only.
    lane_a = [("note", 1), ("note", 2)]
    lane_b = [("note", 1), ("note", 3)]
    scores = _rrf_fuse([lane_a, lane_b], k=60)
    assert scores[("note", 1)] > scores[("note", 2)]
    assert scores[("note", 1)] > scores[("note", 3)]


def test_rrf_fuse_surfaces_single_lane_key():
    # A key present in only one lane still gets a positive score (union, not intersect).
    scores = _rrf_fuse([[("note", 5)], [("note", 9)]], k=60)
    assert scores[("note", 9)] > 0


import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from wizard.models import Note, NoteType
from wizard.repositories.search import SearchRepository


@pytest.fixture
def fts_engine():
    """In-memory engine with FTS5 tables but NO vec table (vec lane must degrade)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5("
            "content, note_type UNINDEXED, content='note', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS note_fts_ai AFTER INSERT ON note BEGIN "
            "INSERT INTO note_fts(rowid, content, note_type) "
            "VALUES (new.id, new.content, new.note_type); END"
        ))
        # hybrid_search's default entity_type=None also scans sessions/meetings/
        # tasks, so those FTS tables need to exist here too (only the vec table
        # is intentionally omitted, to exercise the vec-lane degrade path).
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5("
            "summary, content='wizardsession', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS meeting_fts USING fts5("
            "content, title, content='meeting', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS task_fts USING fts5("
            "name, content='task', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS session_fts_ai AFTER INSERT ON wizardsession BEGIN "
            "INSERT INTO session_fts(rowid, summary) VALUES (new.id, new.summary); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS meeting_fts_ai AFTER INSERT ON meeting BEGIN "
            "INSERT INTO meeting_fts(rowid, content, title) "
            "VALUES (new.id, new.content, new.title); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS task_fts_ai AFTER INSERT ON task BEGIN "
            "INSERT INTO task_fts(rowid, name) VALUES (new.id, new.name); END"
        ))
        conn.commit()
    return engine


def test_phrase_reordered_query_still_matches(fts_engine):
    with Session(fts_engine) as db:
        n = Note(note_type=NoteType.DECISION, content="decided on redis caching for the session store")
        db.add(n)
        db.flush()
        # Old engine required the exact phrase; new engine matches reordered terms.
        results = SearchRepository().hybrid_search(db, "caching redis decision", limit=10)
        assert any(r.entity_id == n.id for r in results)


def test_multi_term_note_outranks_single_term(fts_engine):
    with Session(fts_engine) as db:
        both = Note(note_type=NoteType.INVESTIGATION, content="redis caching layer design")
        one = Note(note_type=NoteType.INVESTIGATION, content="redis connection pool sizing")
        db.add(both)
        db.add(one)
        db.flush()
        results = SearchRepository().hybrid_search(db, "redis caching", limit=10)
        ids = [r.entity_id for r in results]
        assert ids[0] == both.id  # hits both terms -> ranks first


def test_vec_lane_degrades_without_vec_table(fts_engine):
    # No vec_note_embeddings in this engine: must not raise, BM25 still works.
    with Session(fts_engine) as db:
        n = Note(note_type=NoteType.DOCS, content="kafka consumer group rebalance notes")
        db.add(n)
        db.flush()
        results = SearchRepository().hybrid_search(db, "kafka rebalance", limit=10)
        assert any(r.entity_id == n.id for r in results)
