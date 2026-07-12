"""Synthetic recall benchmark for SearchRepository.hybrid_search.

Seeds an isolated corpus into the migrated engine, runs labelled queries per
failure mode, and asserts recall@10 / MRR@10 targets. Semantic-only cases use
a deterministic fake embedding (no model download) so CI is reproducible.

Run as a report:  uv run python -m tests.eval.test_search_recall_benchmark
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories import search as search_mod
from wizard.repositories.search import SearchRepository, serialize_float32

# corpus: id-label -> content
CORPUS = {
    "cache": "decided to cache rendered template fragments in redis",
    "pool": "redis connection pool sizing under load",
    "auth": "jwt decoder monkey-patch failed in the auth middleware",
    "kafka": "kafka consumer group rebalance storms during deploy",
    "feline": "the tabby dozed on the woven floor covering",  # semantic-only target
    "noise1": "quarterly budget spreadsheet reconciliation",
    "noise2": "onboarding checklist for new contractors",
}

# category -> list of (query, set of relevant labels)
CASES = {
    "phrase": [("caching redis fragments decided", {"cache"})],       # reordered
    "word_form": [("caching templates", {"cache"}),
                  ("rebalancing consumers", {"kafka"})],              # inflected
    "multi_term": [("redis caching", {"cache"})],                    # most-terms first
    "semantic_only": [("cat on a rug", {"feline"})],                 # no lexical overlap
}

# Deterministic fake embedding space: label/query -> unit-ish vector.
_VECS = {
    "cat on a rug": [1.0] + [0.0] * 383,
    "feline": [1.0] + [0.0] * 383,
}


def _fake_embed(text_in: str):
    return _VECS.get(text_in.strip())


def _seed(db) -> dict[str, int]:
    ids: dict[str, int] = {}
    for label, content in CORPUS.items():
        # ck_note_has_artifact_ref requires at least one of
        # artifact_id/task_id/session_id/meeting_id to be non-null; give each
        # seeded note a bench-specific artifact_id to satisfy it. This does
        # not affect the words being searched.
        n = Note(note_type=NoteType.INVESTIGATION, content=content, artifact_id=f"bench-{label}")
        db.add(n); db.flush()
        ids[label] = n.id
    # Seed a matching embedding for the semantic-only target only.
    vec = _VECS["feline"]
    db.execute(
        text("INSERT INTO vec_note_embeddings (note_id, embedding) VALUES (:id, :blob)"),
        {"id": ids["feline"], "blob": serialize_float32(vec)},
    )
    db.commit()
    return ids


def _cleanup(db, ids: dict[str, int]) -> None:
    for nid in ids.values():
        db.execute(text("DELETE FROM vec_note_embeddings WHERE note_id = :id"), {"id": nid})
        db.execute(text("DELETE FROM note WHERE id = :id"), {"id": nid})
    db.commit()


def run_benchmark(db, repo) -> dict:
    ids = _seed(db)
    try:
        out: dict = {}
        all_recall, all_rr = [], []
        for cat, cases in CASES.items():
            recalls, rrs = [], []
            for query, rel_labels in cases:
                rel_ids = {ids[l] for l in rel_labels}
                results = repo.hybrid_search(db, query, limit=10)
                got = [r.entity_id for r in results]
                hit = rel_ids.intersection(got)
                recalls.append(1.0 if hit else 0.0)
                rr = 0.0
                for rank, eid in enumerate(got, start=1):
                    if eid in rel_ids:
                        rr = 1.0 / rank
                        break
                rrs.append(rr)
            out[cat] = {
                "recall_at_10": sum(recalls) / len(recalls),
                "mrr_at_10": sum(rrs) / len(rrs),
            }
            all_recall += recalls; all_rr += rrs
        out["aggregate"] = {
            "recall_at_10": sum(all_recall) / len(all_recall),
            "mrr_at_10": sum(all_rr) / len(all_rr),
        }
        return out
    finally:
        _cleanup(db, ids)


def test_recall_benchmark_meets_targets(monkeypatch):
    monkeypatch.setattr(search_mod, "embed", _fake_embed)
    with SASession(engine) as db:
        metrics = run_benchmark(db, SearchRepository())
    assert metrics["phrase"]["recall_at_10"] >= 0.8
    assert metrics["word_form"]["recall_at_10"] >= 0.8
    # >= 0.5 (target in top 2), not == 1.0: the migrated engine is shared with
    # other scenario tests, so a stray matching note could interleave. The
    # two-term note still ranks well above unrelated single-term hits.
    assert metrics["multi_term"]["mrr_at_10"] >= 0.5
    assert metrics["semantic_only"]["recall_at_10"] >= 1.0  # vec-only surfacing works
    assert metrics["aggregate"]["recall_at_10"] >= 0.8


if __name__ == "__main__":
    from unittest.mock import patch
    with patch.object(search_mod, "embed", _fake_embed), SASession(engine) as db:
        metrics = run_benchmark(db, SearchRepository())
    print(f"{'category':<16}{'recall@10':>12}{'mrr@10':>10}")
    for cat, m in metrics.items():
        print(f"{cat:<16}{m['recall_at_10']:>12.2f}{m['mrr_at_10']:>10.2f}")
