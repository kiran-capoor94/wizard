"""Local recall gut-check against the real ~/.wizard/wizard.db (READ-ONLY).

Not part of CI. Fill QUERIES with things you'd actually search for, plus a
substring you expect to see in a relevant note's snippet. Run:

    uv run python scripts/eval_recall_realdb.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session

from wizard.repositories.search import SearchRepository

# (query, expected substring in a relevant result's snippet) — edit these.
QUERIES: list[tuple[str, str]] = [
    ("search recall", "bm25"),
    ("wizard memory noise", "note"),
]

DB = Path.home() / ".wizard" / "wizard.db"


def main() -> int:
    if not DB.exists():
        print(f"No DB at {DB}; nothing to check.")
        return 0
    engine = create_engine(f"sqlite:///{DB}?mode=ro", connect_args={"uri": True})
    repo = SearchRepository()
    with Session(engine) as db:
        for query, expect in QUERIES:
            results = repo.hybrid_search(db, query, limit=10)
            hit = any(expect.lower() in (r.snippet or "").lower() for r in results)
            mark = "HIT " if hit else "miss"
            print(f"[{mark}] {query!r} -> {len(results)} results "
                  f"(expected snippet ~{expect!r})")
            for r in results[:5]:
                print(f"        {r.entity_type}#{r.entity_id}: {r.snippet[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
