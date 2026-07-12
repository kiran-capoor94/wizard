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
