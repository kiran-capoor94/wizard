"""Scenario: wizard hook stop writes OBSERVATION notes from Stop hook input."""
import json
import sqlite3
from unittest.mock import patch

import pytest

from wizard.cli.hooks import (
    _MIN_CONTENT_LEN,
    _resolve_active_task_id,
    _resolve_wizard_session_id,
    _write_observation,
    run_stop_hook,
)
from wizard.cli.main import _extract_last_assistant_message
from wizard.models import NOTE_CONTENT_MAX_CHARS
from wizard.note_hashing import content_hash as compute_content_hash


@pytest.fixture
def tmp_sessions_dir(tmp_path):
    return tmp_path / "sessions"


def test_resolve_wizard_session_id_reads_file(tmp_sessions_dir):
    """_resolve_wizard_session_id reads the integer from the wizard_id file."""
    session_dir = tmp_sessions_dir / "sess_abc"
    session_dir.mkdir(parents=True)
    (session_dir / "wizard_id").write_text("42")

    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        result = _resolve_wizard_session_id("sess_abc")

    assert result == 42


def test_resolve_wizard_session_id_returns_none_if_missing(tmp_sessions_dir):
    """_resolve_wizard_session_id returns None when no wizard_id file exists."""
    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        result = _resolve_wizard_session_id("nonexistent_session")

    assert result is None


def test_resolve_active_task_id_returns_none_when_no_notes(tmp_path):
    """_resolve_active_task_id returns None when no notes exist for the session."""
    db_path = tmp_path / "wizard.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE note (id INTEGER PRIMARY KEY, task_id INTEGER, session_id INTEGER, created_at TEXT)"
        )
    result = _resolve_active_task_id(db_path, wizard_session_id=99)
    assert result is None


def test_resolve_active_task_id_returns_most_recent(tmp_path):
    """_resolve_active_task_id returns the task_id of the most recently saved note,
    skipping NULL task_ids (session-level notes)."""
    db_path = tmp_path / "wizard.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE note (id INTEGER PRIMARY KEY, task_id INTEGER, session_id INTEGER, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO note (task_id, session_id, created_at) VALUES (?, ?, ?)",
            (7, 42, "2026-05-05T10:00:00"),
        )
        conn.execute(
            "INSERT INTO note (task_id, session_id, created_at) VALUES (?, ?, ?)",
            (9, 42, "2026-05-05T11:00:00"),
        )
        # Most recent note has NULL task_id (session-level) — should be skipped
        conn.execute(
            "INSERT INTO note (task_id, session_id, created_at) VALUES (?, ?, ?)",
            (None, 42, "2026-05-05T12:00:00"),
        )
        conn.commit()

    result = _resolve_active_task_id(db_path, wizard_session_id=42)
    assert result == 9  # null-task note skipped, returns last non-null


def test_extract_last_assistant_message_from_jsonl(tmp_path):
    """_extract_last_assistant_message reads the last assistant entry from a JSONL file."""
    transcript = tmp_path / "transcript.jsonl"
    entries = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "short"},
        {"role": "user", "content": "do more"},
        {"role": "assistant", "content": "I investigated the cache invalidation path."},
    ]
    transcript.write_text("\n".join(json.dumps(e) for e in entries))

    result = _extract_last_assistant_message(transcript)
    assert result == "I investigated the cache invalidation path."


def test_extract_last_assistant_message_handles_list_content(tmp_path):
    """_extract_last_assistant_message joins text parts from list-content entries."""
    transcript = tmp_path / "transcript.jsonl"
    entry = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Part one."},
            {"type": "tool_use", "id": "x"},
            {"type": "text", "text": "Part two."},
        ],
    }
    transcript.write_text(json.dumps(entry))

    result = _extract_last_assistant_message(transcript)
    assert result == "Part one. Part two."


def test_extract_last_assistant_message_returns_empty_for_missing_file(tmp_path):
    """_extract_last_assistant_message returns empty string when file doesn't exist."""
    result = _extract_last_assistant_message(tmp_path / "nonexistent.jsonl")
    assert result == ""


def test_run_stop_hook_exits_silently_with_no_wizard_id(tmp_sessions_dir, tmp_path):
    """run_stop_hook does nothing and does not raise when wizard_id file is missing."""
    db_path = tmp_path / "wizard.db"
    db_path.touch()

    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        mock_settings.db = str(db_path)
        run_stop_hook("nonexistent_session", "A" * 100)
    # No exception = pass


def test_run_stop_hook_ignores_short_messages(tmp_sessions_dir, tmp_path):
    """run_stop_hook returns early for messages shorter than _MIN_CONTENT_LEN."""
    short = "x" * (_MIN_CONTENT_LEN - 1)

    with patch("wizard.cli.hooks._resolve_wizard_session_id") as mock_resolve:
        run_stop_hook("any_session", short)
        mock_resolve.assert_not_called()


def test_run_stop_hook_truncates_oversized_message(tmp_sessions_dir, tmp_path):
    """An assistant message longer than NOTE_CONTENT_MAX_CHARS must be truncated
    before being written — this hook has no other size guard on stored content."""
    session_dir = tmp_sessions_dir / "sess_big"
    session_dir.mkdir(parents=True)
    (session_dir / "wizard_id").write_text("1")

    db_path = tmp_path / "wizard.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE note (id INTEGER PRIMARY KEY, note_type TEXT, content TEXT,"
            " content_hash TEXT, status TEXT NOT NULL DEFAULT 'active', task_id INTEGER, session_id INTEGER,"
            " created_at TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE task_state (task_id INTEGER PRIMARY KEY, note_count INTEGER,"
            " observation_count INTEGER, last_note_at TEXT, last_touched_at TEXT, stale_days INTEGER)"
        )
        conn.execute(
            "INSERT INTO note (task_id, session_id, status, created_at) VALUES (?, ?, 'active', ?)",
            (7, 1, "2026-05-05T10:00:00"),
        )
        conn.execute("INSERT INTO task_state (task_id) VALUES (7)")
        conn.commit()

    oversized = "x" * (NOTE_CONTENT_MAX_CHARS + 500)

    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        mock_settings.db = str(db_path)
        run_stop_hook("sess_big", oversized)

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT content FROM note WHERE note_type = 'OBSERVATION'"
        ).fetchone()
    assert len(row[0]) == NOTE_CONTENT_MAX_CHARS


def test_write_observation_truncated_content_stored_as_is(tmp_path):
    """_write_observation itself performs no truncation — the caller is responsible."""
    db_path = tmp_path / "wizard.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE note (id INTEGER PRIMARY KEY, note_type TEXT, content TEXT,"
            " content_hash TEXT, status TEXT NOT NULL DEFAULT 'active', task_id INTEGER, session_id INTEGER,"
            " created_at TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE task_state (task_id INTEGER PRIMARY KEY, note_count INTEGER,"
            " observation_count INTEGER, last_note_at TEXT, last_touched_at TEXT, stale_days INTEGER)"
        )
        conn.execute("INSERT INTO task_state (task_id) VALUES (7)")
        conn.commit()

    _write_observation(
        db_path,
        task_id=7,
        session_id=1,
        content="already-capped content",
        content_hash=compute_content_hash("already-capped content"),
    )

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT content FROM note WHERE task_id = 7").fetchone()
    assert row[0] == "already-capped content"


def _seed_hook_db(db_path, task_id=7):
    """Create the note/task_state schema used by run_stop_hook and seed a prior
    session-note so `_resolve_active_task_id` can find the task."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE note (id INTEGER PRIMARY KEY, note_type TEXT, content TEXT,"
            " content_hash TEXT, status TEXT NOT NULL DEFAULT 'active', task_id INTEGER, session_id INTEGER,"
            " created_at TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE task_state (task_id INTEGER PRIMARY KEY, note_count INTEGER,"
            " observation_count INTEGER, last_note_at TEXT, last_touched_at TEXT, stale_days INTEGER)"
        )
        conn.execute(
            "INSERT INTO note (task_id, session_id, status, created_at) VALUES (?, ?, 'active', ?)",
            (task_id, 1, "2026-05-05T10:00:00"),
        )
        conn.execute("INSERT INTO task_state (task_id) VALUES (?)", (task_id,))
        conn.commit()


def test_run_stop_hook_pii_scrubs_observation(tmp_sessions_dir, tmp_path):
    """The newest OBSERVATION note's content is PII-scrubbed, not the raw message."""
    session_dir = tmp_sessions_dir / "sess_pii"
    session_dir.mkdir(parents=True)
    (session_dir / "wizard_id").write_text("1")

    db_path = tmp_path / "wizard.db"
    _seed_hook_db(db_path)

    message = "Investigated the outage and emailed user@example.com about the fix for the timeout bug."

    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        mock_settings.db = str(db_path)
        run_stop_hook("sess_pii", message)

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT content FROM note WHERE note_type = 'OBSERVATION'"
        ).fetchone()
    assert row is not None
    assert row[0] != message
    assert "user@example.com" not in row[0]


def test_run_stop_hook_sets_content_hash(tmp_sessions_dir, tmp_path):
    """The OBSERVATION note's content_hash equals content_hash(scrubbed_content)."""
    session_dir = tmp_sessions_dir / "sess_hash"
    session_dir.mkdir(parents=True)
    (session_dir / "wizard_id").write_text("1")

    db_path = tmp_path / "wizard.db"
    _seed_hook_db(db_path)

    message = "Root-caused the timeout to a missing index on the tasks.status column entirely."

    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        mock_settings.db = str(db_path)
        run_stop_hook("sess_hash", message)

    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT content, content_hash FROM note WHERE note_type = 'OBSERVATION'"
        ).fetchone()
    assert row is not None
    assert row[1] == compute_content_hash(row[0])


def test_run_stop_hook_dedups_verbatim_repeat(tmp_sessions_dir, tmp_path):
    """Calling run_stop_hook twice with the same message writes only one OBSERVATION note."""
    session_dir = tmp_sessions_dir / "sess_dedup"
    session_dir.mkdir(parents=True)
    (session_dir / "wizard_id").write_text("1")

    db_path = tmp_path / "wizard.db"
    _seed_hook_db(db_path)

    message = "Same finding reported twice: the retry logic double-submits payment requests."

    with patch("wizard.cli.hooks.settings") as mock_settings:
        mock_settings.paths.sessions_dir = tmp_sessions_dir
        mock_settings.db = str(db_path)
        run_stop_hook("sess_dedup", message)
        run_stop_hook("sess_dedup", message)

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT id FROM note WHERE note_type = 'OBSERVATION'"
        ).fetchall()
    assert len(rows) == 1
