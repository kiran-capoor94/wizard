"""Behaviour tests for the recall-engine rewrite of SearchRepository."""
from wizard.repositories.search import _build_fts_query


def test_build_fts_query_ors_prefix_terms():
    assert _build_fts_query("redis caching decision") == '"redis"* OR "caching"* OR "decision"*'


def test_build_fts_query_splits_on_punctuation():
    assert _build_fts_query("monkey-patch auth!") == '"monkey"* OR "patch"* OR "auth"*'


def test_build_fts_query_empty_when_no_word_chars():
    assert _build_fts_query("   ") == ""
    assert _build_fts_query("!!! ??? ") == ""
