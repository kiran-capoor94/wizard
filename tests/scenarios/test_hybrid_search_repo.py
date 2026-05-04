"""Behaviour tests for SearchRepository.hybrid_search()."""
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.repositories.search import SearchRepository, _bm25_score, _cosine_score


def test_bm25_score_negative_rank():
    # rank=-1.0 → 1/(1-(-1)) = 0.5
    assert abs(_bm25_score(-1.0) - 0.5) < 1e-9


def test_cosine_score_zero_distance():
    # distance=0 → 1.0 (identical vectors)
    assert _cosine_score(0.0) == 1.0


def test_cosine_score_max_distance():
    # distance=2 → 0.0 (opposite vectors)
    assert _cosine_score(2.0) == 0.0


def test_hybrid_search_empty_query_returns_empty():
    repo = SearchRepository()
    with SASession(engine) as db:
        results = repo.hybrid_search(db, "   ")
    assert results == []


def test_hybrid_search_no_results_for_nonexistent_term():
    repo = SearchRepository()
    with SASession(engine) as db:
        results = repo.hybrid_search(db, "zzz_nonexistent_xqy_term_9999")
    assert results == []
