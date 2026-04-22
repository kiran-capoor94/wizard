#!/usr/bin/env python3
"""Retroactively synthesise wizard sessions.

By default processes ALL sessions with a reachable transcript, regardless of
is_synthesised state. Resets is_synthesised=False before each run so capture
doesn't skip already-marked sessions.

Usage:
    uv run python scripts/backfill_synthesis.py
    uv run python scripts/backfill_synthesis.py --dry-run
    uv run python scripts/backfill_synthesis.py --session-id 464
"""

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

try:
    from wizard.cli.capture import capture as capture_cli
except ImportError:
    print("Error: Could not import wizard. Ensure you are running via 'uv run'.", file=sys.stderr)
    sys.exit(1)


def _find_db() -> Path:
    env = os.environ.get("WIZARD_DB")
    if env:
        return Path(env)
    return Path.home() / ".wizard" / "wizard.db"


def _find_transcript(agent_session_id: str) -> Path | None:
    matches = list(Path.home().glob(f".claude/projects/*/{agent_session_id}.jsonl"))
    return matches[0] if matches else None


def _get_transcript_raw(db_path: Path, session_id: int) -> str | None:
    """Return stored transcript_raw content for the session, if any."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT transcript_raw FROM wizardsession WHERE id = ?", (session_id,)
        ).fetchone()
    return row[0] if row and row[0] else None


def _reset_synthesised(db_path: Path, session_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE wizardsession SET is_synthesised = 0 WHERE id = ?", (session_id,))
        conn.commit()


def _synthesise_session(
    db_path: Path,
    sid: int,
    path: Path | None,
    agent: str | None,
    raw_or_flag: str | bool,
) -> tuple[int, int]:
    """Run capture_cli for one session. Returns (ok, failed) increment."""
    _reset_synthesised(db_path, sid)

    tmp_path: Path | None = None
    if path is None and raw_or_flag:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(str(raw_or_flag))
            tmp_path = Path(tmp.name)
        path = tmp_path

    start = time.monotonic()
    try:
        capture_cli(
            close=True,
            transcript=str(path),
            agent=agent or "claude-code",
            session_id=sid,
            agent_session_id=None,
        )
        elapsed = time.monotonic() - start
        print(f"ok ({elapsed:.2f}s)")
        return 1, 0
    except SystemExit as e:
        elapsed = time.monotonic() - start
        if e.code == 0:
            print(f"ok ({elapsed:.2f}s)")
            return 1, 0
        print(f"FAILED ({elapsed:.2f}s) - Exit code {e.code}")
        return 0, 1
    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"FAILED ({elapsed:.2f}s)\n    {e}")
        return 0, 1
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _query_rows(db_path: Path, session_id: int | None) -> list:
    with sqlite3.connect(db_path) as conn:
        if session_id is not None:
            rows = conn.execute(
                "SELECT id, transcript_path, agent_session_id, agent"
                " FROM wizardsession WHERE id = ?",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, transcript_path, agent_session_id, agent
                FROM wizardsession
                WHERE transcript_path IS NOT NULL OR agent_session_id IS NOT NULL
                ORDER BY created_at ASC
                """
            ).fetchall()
    return rows


def _resolve_sessions(db_path: Path, rows: list) -> list:
    """Resolve each row to a (sid, path, agent, raw_or_flag) tuple."""
    to_process = []
    for sid, transcript_path, agent_session_id, agent in rows:
        path: Path | None = None
        if transcript_path and Path(transcript_path).exists():
            path = Path(transcript_path)
        elif agent_session_id:
            path = _find_transcript(agent_session_id)

        if path:
            to_process.append((sid, path, agent, False))
        else:
            raw = _get_transcript_raw(db_path, sid)
            if raw:
                to_process.append((sid, None, agent, raw))
            else:
                print(
                    f"  [{sid}] WARNING: transcript not found and no stored raw content "
                    f"(path={transcript_path}, agent_session_id={agent_session_id})"
                )
    return to_process


def backfill(dry_run: bool = False, session_id: int | None = None) -> None:
    db_path = _find_db()
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    start_time_total = time.monotonic()
    rows = _query_rows(db_path, session_id)

    if not rows:
        print("No sessions found.")
        return

    to_process = _resolve_sessions(db_path, rows)

    if not to_process:
        print("No sessions with reachable transcripts.")
        return

    print(f"\nFound {len(to_process)} session(s) to synthesise.\n")

    ok = failed = 0

    for sid, path, agent, raw_or_flag in to_process:
        label = path.name if path else "(stored raw content)"
        print(f"  [{sid}] {label} ... ", end="", flush=True)

        if dry_run:
            print("(dry-run)")
            ok += 1
            continue

        ok_inc, fail_inc = _synthesise_session(db_path, sid, path, agent, raw_or_flag)
        ok += ok_inc
        failed += fail_inc
        time.sleep(0.5)

    total_elapsed = time.monotonic() - start_time_total
    suffix = " (dry-run)" if dry_run else ""
    print(f"\n{ok} synthesised{suffix}, {failed} failed. Total time: {total_elapsed:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would run, without running it"
    )
    parser.add_argument(
        "--session-id", type=int, default=None, help="Re-synthesise a single session by ID"
    )
    args = parser.parse_args()
    backfill(dry_run=args.dry_run, session_id=args.session_id)
