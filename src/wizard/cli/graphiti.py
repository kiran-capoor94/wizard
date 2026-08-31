"""Backfill existing SQLite notes/sessions/meetings into the shared Graphiti graph.

NOT idempotent. An earlier version claimed idempotency via "Graphiti's uuid
upsert", but graphiti-core 0.22.0 has no such upsert: add_episode(uuid=...)
looks up an EXISTING episode and raises NodeNotFoundError otherwise, killing
the service's ingest worker. Episodes are therefore created without a uuid,
and re-running this command creates duplicates. Clear the group first
(DELETE /group/{group_id}) if you need a clean rebuild.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

import typer
from sqlalchemy import text

from wizard.config import settings
from wizard.graph_memory import episode_uuid, meeting_body, note_body, session_body

logger = logging.getLogger(__name__)


def run_backfill_graphiti(
    client: Any,
    enabled: bool,
    db: Any,
    security: Any,
    batch_size: int | None = None,
    pause_seconds: float | None = None,
    sleep: Any = time.sleep,
) -> None:
    """Push all active notes, closed sessions, and meetings into Graphiti.

    Dependencies are passed as parameters (rather than resolved internally)
    so this is unit-testable without a live Graphiti service or database —
    the Typer command wires the real ones. Submissions are paced in batches
    (see `_paced_push`) so a serial graph worker isn't overrun and OOM-killed.
    """
    if not enabled:
        typer.echo("Graphiti is disabled (settings.graphiti.enabled=false). Nothing to do.")
        return

    batch_size = batch_size if batch_size is not None else settings.graphiti.backfill_batch_size
    pause_seconds = (
        pause_seconds if pause_seconds is not None else settings.graphiti.backfill_pause_seconds
    )

    # Each phase is isolated: one malformed historical row must not cost the
    # other phases. Previously a single NULL timestamp in the session phase
    # aborted the command and the meetings phase never ran at all.
    counts: dict[str, int] = {}
    failures: dict[str, str] = {}
    for label, fn in (
        ("note", _backfill_notes),
        ("session", _backfill_sessions),
        ("meeting", _backfill_meetings),
    ):
        try:
            counts[label] = fn(client, db, security, batch_size, pause_seconds, sleep)
        except Exception as e:  # noqa: BLE001 - report and continue to next phase
            counts[label] = 0
            failures[label] = f"{type(e).__name__}: {e}"
            logger.exception("Graphiti backfill phase failed: %s", label)

    typer.echo(
        f"Backfill complete. Pushed {counts['note']} note episode(s), "
        f"{counts['session']} session episode(s), {counts['meeting']} meeting episode(s)."
    )
    for label, err in failures.items():
        typer.echo(f"  {label} phase FAILED: {err}", err=True)


def _paced_push(
    client: Any,
    episodes: list[dict[str, Any]],
    batch_size: int,
    pause_seconds: float,
    sleep: Any = time.sleep,
) -> int:
    """Submit episodes in batches, pausing between batches so the serial
    graph worker can drain (prevents producer-outrunning-consumer OOM)."""
    pushed = 0
    total = len(episodes)
    for i in range(0, total, batch_size):
        batch = episodes[i : i + batch_size]
        for ep in batch:
            client.add_episode(**ep)
            pushed += 1
        typer.echo(f"backfill: {pushed}/{total} episodes submitted...")
        if i + batch_size < total:  # no trailing sleep after the last batch
            sleep(pause_seconds)
    return pushed


def _scrub(security: Any, value: str | None) -> str | None:
    if value is None:
        return None
    return security.scrub(value).clean if security else value


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _backfill_notes(
    client: Any, db: Any, security: Any, batch_size: int, pause_seconds: float, sleep: Any
) -> int:
    rows = db.execute(
        text(
            "SELECT id, note_type, content, mental_model, task_id, session_id, created_at "
            "FROM note WHERE status = 'active'"
        )
    ).mappings().fetchall()

    episodes = [
        {
            "name": episode_uuid("note", r["id"]),
            "body": note_body(
                note_type=r["note_type"],
                content=_scrub(security, r["content"]),
                mental_model=r["mental_model"],
                task_id=r["task_id"],
                session_id=r["session_id"],
                supersedes_note_id=None,
            ),
            "reference_time": _ts(r["created_at"]),
            "source_description": "wizard:note",
        }
        for r in rows
    ]
    return _paced_push(client, episodes, batch_size, pause_seconds, sleep)


def _backfill_sessions(
    client: Any, db: Any, security: Any, batch_size: int, pause_seconds: float, sleep: Any
) -> int:
    # Sessions whose session_state is NULL were never cleanly closed (M2's
    # SessionCloser only populates it on close) — nothing to push for those.
    rows = db.execute(
        text(
            # last_active_at is nullable and is NULL for every historical row;
            # created_at/updated_at are NOT NULL. Without the COALESCE, _ts()
            # raised ValueError on the first row and aborted the whole backfill,
            # taking the meetings phase with it.
            "SELECT id, session_state, "
            "COALESCE(last_active_at, updated_at, created_at) AS reference_time "
            "FROM wizardsession WHERE session_state IS NOT NULL"
        )
    ).mappings().fetchall()

    episodes = []
    for r in rows:
        state = json.loads(r["session_state"])
        # Scrub is already applied at write-time (session_end) — re-scrubbing
        # here is defensive and idempotent (scrubbed text re-scrubs to itself).
        episodes.append({
            "name": episode_uuid("session", r["id"]),
            "body": session_body(
                intent=_scrub(security, state["intent"]),
                state_delta=_scrub(security, state["state_delta"]),
                open_loops=state.get("open_loops", []),
                next_actions=state.get("next_actions", []),
                closure_status=state["closure_status"],
            ),
            "reference_time": _ts(r["reference_time"]),
            "source_description": "wizard:session",
        })
    return _paced_push(client, episodes, batch_size, pause_seconds, sleep)


def _backfill_meetings(
    client: Any, db: Any, security: Any, batch_size: int, pause_seconds: float, sleep: Any
) -> int:
    rows = db.execute(
        text("SELECT id, title, category, content, summary, created_at FROM meeting")
    ).mappings().fetchall()

    episodes = [
        {
            "name": episode_uuid("meeting", r["id"]),
            "body": meeting_body(
                title=_scrub(security, r["title"]),
                category=r["category"],
                content=_scrub(security, r["content"]),
                summary=_scrub(security, r["summary"]),
            ),
            "reference_time": _ts(r["created_at"]),
            "source_description": "wizard:meeting",
        }
        for r in rows
    ]
    return _paced_push(client, episodes, batch_size, pause_seconds, sleep)
