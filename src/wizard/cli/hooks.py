"""Stop hook handler — writes last assistant message as OBSERVATION note."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from wizard.config import settings
from wizard.models import NOTE_CONTENT_MAX_CHARS, NoteType
from wizard.security import is_safe_session_id

logger = logging.getLogger(__name__)

_MIN_CONTENT_LEN = 50  # ignore trivially short messages


def run_stop_hook(agent_session_id: str, last_message: str) -> None:
    """Write last assistant message as OBSERVATION note. <150ms, no LLM."""
    if len(last_message) < _MIN_CONTENT_LEN:
        return
    if not is_safe_session_id(agent_session_id):
        logger.debug("hook: unsafe agent_session_id %r — ignoring", agent_session_id)
        return
    try:
        wizard_session_id = _resolve_wizard_session_id(agent_session_id)
        if wizard_session_id is None:
            return

        db_path = Path(settings.db)
        if not db_path.exists():
            return

        task_id = _resolve_active_task_id(db_path, wizard_session_id)
        if task_id is None:
            return

        _write_observation(
            db_path, task_id, wizard_session_id, last_message[:NOTE_CONTENT_MAX_CHARS]
        )
    except Exception as e:
        logger.debug("hook: run_stop_hook failed: %s", e)


def _resolve_wizard_session_id(agent_session_id: str) -> int | None:
    """Read wizard integer session ID from the keyed directory written by session_start."""
    id_file = settings.paths.sessions_dir / agent_session_id / "wizard_id"
    try:
        return int(id_file.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _resolve_active_task_id(db_path: Path, wizard_session_id: int) -> int | None:
    """Return the task_id of the most recently saved note for this session, or None."""
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            row = conn.execute(
                "SELECT task_id FROM note"
                " WHERE session_id = ? AND task_id IS NOT NULL"
                " ORDER BY created_at DESC LIMIT 1",
                (wizard_session_id,),
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.debug("hook: failed to resolve active task_id: %s", e)
        return None


def _write_observation(
    db_path: Path, task_id: int, session_id: int, content: str
) -> None:
    """Insert OBSERVATION note and update task_state counts."""
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute(
                "INSERT INTO note (note_type, content, task_id, session_id, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (NoteType.OBSERVATION.value, content, task_id, session_id, now, now),
            )
            conn.execute(
                """
                UPDATE task_state
                SET note_count = COALESCE(note_count, 0) + 1,
                    observation_count = COALESCE(observation_count, 0) + 1,
                    last_note_at = ?,
                    last_touched_at = ?,
                    stale_days = 0
                WHERE task_id = ?
                """,
                (now, now, task_id),
            )
            conn.commit()
    except Exception as e:
        logger.debug("hook: failed to write observation: %s", e)
