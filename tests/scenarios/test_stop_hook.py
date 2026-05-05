"""Scenario: wizard hook stop writes OBSERVATION notes from Stop hook input."""
import sqlite3
from unittest.mock import patch

import pytest

from wizard.cli.hooks import (
    _MIN_CONTENT_LEN,
    _resolve_active_task_id,
    _resolve_wizard_session_id,
    run_stop_hook,
)


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
    """_resolve_active_task_id returns the task_id of the most recently saved note."""
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
        conn.commit()

    result = _resolve_active_task_id(db_path, wizard_session_id=42)
    assert result == 9


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
