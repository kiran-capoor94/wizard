"""Read-only note corpus-health audit against the real ~/.wizard/wizard.db.

Not part of CI. Run before/after Phase 2 to see the noise drop:
    uv run python scripts/audit_note_quality.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

DB = Path.home() / ".wizard" / "wizard.db"


def main() -> int:
    if not DB.exists():
        print(f"No DB at {DB}; nothing to audit.")
        return 0
    engine = create_engine(f"sqlite:///{DB}?mode=ro", connect_args={"uri": True})
    with engine.connect() as c:
        total = c.execute(text("SELECT count(*) FROM note")).scalar() or 0
        by_type = c.execute(text(
            "SELECT note_type, count(*) FROM note GROUP BY note_type")).all()
        by_status = c.execute(text(
            "SELECT status, count(*) FROM note GROUP BY status")).all()
        boilerplate = c.execute(text(
            "SELECT count(*) FROM note WHERE content LIKE 'Auto-closed:%'")).scalar() or 0
        anchored = c.execute(text(
            "SELECT count(*) FROM note WHERE task_id IS NOT NULL")).scalar() or 0
        exact_dups = c.execute(text(
            "SELECT count(*) FROM (SELECT content FROM note GROUP BY content HAVING count(*)>1)"
        )).scalar() or 0
        null_hash = c.execute(text(
            "SELECT count(*) FROM note WHERE content_hash IS NULL")).scalar() or 0

    def pct(n):
        return f"{(100 * n / total):.0f}%" if total else "0%"

    print(f"notes: {total}")
    print("  by type:   " + ", ".join(f"{t}={n}" for t, n in by_type))
    print("  by status: " + ", ".join(f"{s}={n}" for s, n in by_status))
    print(f"  boilerplate (Auto-closed:): {boilerplate} ({pct(boilerplate)})")
    print(f"  task-anchored: {anchored} ({pct(anchored)})")
    print(f"  exact-duplicate content groups: {exact_dups}")
    print(f"  null content_hash (un-deduped): {null_hash}")
    demoted = sum(n for s, n in by_status if s != "active")
    print(f"  demoted (non-active): {demoted} ({pct(demoted)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
