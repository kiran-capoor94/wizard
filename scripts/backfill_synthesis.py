#!/usr/bin/env python3
"""Retroactively synthesise all unsynthesised wizard sessions.

Finds every session where is_synthesised=False and a transcript is available
(either stored in transcript_path or locatable via agent_session_id), and runs
`wizard capture --close` for each one. Sessions that already have a summary are
included — synthesis generates structured notes even when a summary exists.

Usage:
    uv run python scripts/backfill_synthesis.py
    uv run python scripts/backfill_synthesis.py --dry-run
"""

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _find_db() -> Path:
    env = os.environ.get("WIZARD_DB")
    if env:
        return Path(env)
    return Path.home() / ".wizard" / "wizard.db"


def _find_transcript(agent_session_id: str) -> Path | None:
    matches = list(Path.home().glob(f".claude/projects/*/{agent_session_id}.jsonl"))
    return matches[0] if matches else None


def backfill(dry_run: bool = False) -> None:
    db_path = _find_db()
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT id, transcript_path, agent_session_id
        FROM wizardsession
        WHERE is_synthesised = 0
          AND (transcript_path IS NOT NULL OR agent_session_id IS NOT NULL)
        ORDER BY created_at ASC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("No unsynthesised sessions found.")
        return

    print(f"Found {len(rows)} unsynthesised session(s).\n")

    ok = skipped = failed = 0

    for session_id, transcript_path, agent_session_id in rows:
        path: Path | None = None
        if transcript_path and Path(transcript_path).exists():
            path = Path(transcript_path)
        elif agent_session_id:
            path = _find_transcript(agent_session_id)

        if path is None:
            print(f"  [{session_id}] no transcript — skipping")
            skipped += 1
            continue

        cmd = [
            "uv", "run", "wizard", "capture", "--close",
            "--session-id", str(session_id),
            "--agent", "claude-code",
            "--transcript", str(path),
        ]
        print(f"  [{session_id}] {path.name}", end=" ... ", flush=True)

        if dry_run:
            print("(dry-run)")
            ok += 1
            continue

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout.strip() or "ok")
            ok += 1
        else:
            print(f"FAILED\n    {(result.stderr or result.stdout).strip()}")
            failed += 1

    suffix = " (dry-run)" if dry_run else ""
    print(f"\n{ok} synthesised{suffix}, {skipped} skipped (no transcript), {failed} failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would run, without running it")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
