"""Scenario: doctor's FTS trigger check catches the class of bug that broke
note/session search (a batch_alter_table on note/wizardsession silently
dropped their FTS sync triggers)."""

import sqlite3

from wizard.cli.doctor import REQUIRED_FTS_TRIGGERS, _check_fts_triggers


def test_fts_trigger_check_passes_when_all_present(tmp_path, monkeypatch):
    db_path = tmp_path / "wizard.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE note (id INTEGER PRIMARY KEY)")
        for trigger in REQUIRED_FTS_TRIGGERS:
            conn.execute(f"CREATE TRIGGER {trigger} AFTER INSERT ON note BEGIN SELECT 1; END")
        conn.commit()
    monkeypatch.setattr("wizard.cli.doctor.settings.db", str(db_path))

    passed, message = _check_fts_triggers()
    assert passed, message


def test_fts_trigger_check_fails_when_note_triggers_missing(tmp_path, monkeypatch):
    """Reproduces the exact regression: note/session triggers gone, meeting/task intact."""
    db_path = tmp_path / "wizard.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE note (id INTEGER PRIMARY KEY)")
        for trigger in ["meeting_fts_ai", "meeting_fts_ad", "meeting_fts_au",
                        "task_fts_ai", "task_fts_ad", "task_fts_au"]:
            conn.execute(f"CREATE TRIGGER {trigger} AFTER INSERT ON note BEGIN SELECT 1; END")
        conn.commit()
    monkeypatch.setattr("wizard.cli.doctor.settings.db", str(db_path))

    passed, message = _check_fts_triggers()
    assert not passed
    assert "note_fts_ai" in message
    assert "session_fts_ai" in message


def test_fts_trigger_check_skips_when_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("wizard.cli.doctor.settings.db", str(tmp_path / "nonexistent.db"))

    passed, message = _check_fts_triggers()
    assert passed
    assert "not found" in message.lower()
