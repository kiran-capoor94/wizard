"""Behaviour tests for SearchRepository.hybrid_search()."""
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
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
