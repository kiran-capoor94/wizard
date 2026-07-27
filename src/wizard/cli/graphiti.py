"""Backfill existing SQLite notes/sessions/meetings into the shared Graphiti graph.

Idempotency comes for free from Graphiti's uuid upsert (see
wizard.graph_memory.episode_uuid) — re-running this command pushes the same
uuids and simply overwrites the same episodes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import typer
from sqlalchemy import text

from wizard.graph_memory import meeting_body, note_body, session_body

logger = logging.getLogger(__name__)


def run_backfill_graphiti(client: Any, enabled: bool, db: Any, security: Any) -> None:
    """Push all active notes, closed sessions, and meetings into Graphiti.

    Dependencies are passed as parameters (rather than resolved internally)
    so this is unit-testable without a live Graphiti service or database —
    the Typer command wires the real ones.
    """
    if not enabled:
        typer.echo("Graphiti is disabled (settings.graphiti.enabled=false). Nothing to do.")
        return

    notes = _backfill_notes(client, db, security)
    sessions = _backfill_sessions(client, db, security)
    meetings = _backfill_meetings(client, db, security)

    typer.echo(
        f"Backfill complete. Pushed {notes} note episode(s), "
        f"{sessions} session episode(s), {meetings} meeting episode(s)."
    )


def _scrub(security: Any, value: str | None) -> str | None:
    if value is None:
        return None
    return security.scrub(value).clean if security else value


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _backfill_notes(client: Any, db: Any, security: Any) -> int:
    rows = db.execute(
        text(
            "SELECT id, note_type, content, mental_model, task_id, session_id, created_at "
            "FROM note WHERE status = 'active'"
        )
    ).mappings().fetchall()

    pushed = 0
    for r in rows:
        client.add_episode(
            name=f"note {r['id']}",
            body=note_body(
                note_type=r["note_type"],
                content=_scrub(security, r["content"]),
                mental_model=r["mental_model"],
                task_id=r["task_id"],
                session_id=r["session_id"],
                supersedes_note_id=None,
            ),
            reference_time=_ts(r["created_at"]),
            uuid=f"wizard-note-{r['id']}",
            source_description="wizard:note",
        )
        pushed += 1
    return pushed


def _backfill_sessions(client: Any, db: Any, security: Any) -> int:
    # Sessions whose session_state is NULL were never cleanly closed (M2's
    # SessionCloser only populates it on close) — nothing to push for those.
    rows = db.execute(
        text(
            "SELECT id, session_state, last_active_at FROM wizardsession "
            "WHERE session_state IS NOT NULL"
        )
    ).mappings().fetchall()

    pushed = 0
    for r in rows:
        state = json.loads(r["session_state"])
        # Scrub is already applied at write-time (session_end) — re-scrubbing
        # here is defensive and idempotent (scrubbed text re-scrubs to itself).
        client.add_episode(
            name=f"session {r['id']}",
            body=session_body(
                intent=_scrub(security, state["intent"]),
                state_delta=_scrub(security, state["state_delta"]),
                open_loops=state.get("open_loops", []),
                next_actions=state.get("next_actions", []),
                closure_status=state["closure_status"],
            ),
            reference_time=_ts(r["last_active_at"]),
            uuid=f"wizard-session-{r['id']}",
            source_description="wizard:session",
        )
        pushed += 1
    return pushed


def _backfill_meetings(client: Any, db: Any, security: Any) -> int:
    rows = db.execute(
        text("SELECT id, title, category, content, summary, created_at FROM meeting")
    ).mappings().fetchall()

    pushed = 0
    for r in rows:
        client.add_episode(
            name=f"meeting {r['id']}",
            body=meeting_body(
                title=_scrub(security, r["title"]),
                category=r["category"],
                content=_scrub(security, r["content"]),
                summary=_scrub(security, r["summary"]),
            ),
            reference_time=_ts(r["created_at"]),
            uuid=f"wizard-meeting-{r['id']}",
            source_description="wizard:meeting",
        )
        pushed += 1
    return pushed
