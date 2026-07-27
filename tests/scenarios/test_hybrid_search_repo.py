"""Behaviour tests for SearchRepository.hybrid_search()."""
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteStatus, NoteType
from wizard.repositories import NoteRepository
from wizard.repositories import search as search_mod
from wizard.repositories.search import SearchRepository


def test_hybrid_search_empty_query_returns_empty():
    repo = SearchRepository()
    with SASession(engine) as db:
        results = repo.hybrid_search(db, "   ")
    assert results == []


def test_hybrid_search_no_results_for_nonexistent_term(monkeypatch):
    # Force embedding off so only BM25 runs -> a truly novel term yields nothing.
    monkeypatch.setattr(search_mod, "embed", lambda _text: None)
    repo = SearchRepository()
    with SASession(engine) as db:
        results = repo.hybrid_search(db, "zzz_nonexistent_xqy_term_9999")
    assert results == []


def test_fetch_by_keys_preserves_order_and_drops_missing(db_session):
    note = Note(
        note_type=NoteType.DECISION,
        content="use WAL",
        status=NoteStatus.ACTIVE,
    )
    saved = NoteRepository().save(db_session, note)

    repo = SearchRepository()
    out = repo.fetch_by_keys(db_session, [("note", saved.id), ("note", 99999)])

    assert [(r.entity_type, r.entity_id) for r in out] == [("note", saved.id)]
