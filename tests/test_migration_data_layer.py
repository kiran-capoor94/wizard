"""Migration smoke test for the task_state / mental_model / session_state
release. Runs alembic upgrade against a scratch SQLite file, seeds rows
at the previous head, applies this migration, and verifies backfill +
downgrade behaviour."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlmodel import SQLModel


PREVIOUS_HEAD = "15146de1d71a"  # add toolcall table
NEW_HEAD = "c821b5437485"  # add task_state mental_model session_state


def _alembic_config(db_path: Path) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _rewire_wizard_to(db_path: Path, tmp_path: Path) -> None:
    """Rewrite wizard config + reimport so env.py's engine points at db_path."""
    import os

    config_file = tmp_path / "migration_config.json"
    config_file.write_text(json.dumps({"db": str(db_path)}))
    os.environ["WIZARD_CONFIG_FILE"] = str(config_file)

    for mod in list(sys.modules):
        if mod.startswith("wizard"):
            del sys.modules[mod]

    SQLModel.metadata.clear()
    SQLModel._sa_registry.dispose(cascade=True)

    import wizard.models  # noqa: F401 — re-registers models


@pytest.fixture
def scratch_db(tmp_path):
    db_path = tmp_path / "test.db"
    _rewire_wizard_to(db_path, tmp_path)
    yield db_path


def test_upgrade_creates_task_state_table_and_new_columns(scratch_db, tmp_path):
    cfg = _alembic_config(scratch_db)
    command.upgrade(cfg, PREVIOUS_HEAD)

    # Seed: two tasks, one with notes (one decision, one investigation),
    # one with no notes.
    conn = sqlite3.connect(str(scratch_db))
    conn.executescript(
        "INSERT INTO task (id, name, priority, category, status, "
        "created_at, updated_at) VALUES "
        "(1, 'with-notes', 'medium', 'issue', 'todo', "
        " '2026-04-01 10:00:00', '2026-04-01 10:00:00'), "
        "(2, 'no-notes', 'low', 'issue', 'todo', "
        " '2026-04-05 10:00:00', '2026-04-05 10:00:00');"
        "INSERT INTO note (id, note_type, content, task_id, "
        "created_at, updated_at) VALUES "
        "(10, 'investigation', 'i1', 1, "
        " '2026-04-02 12:00:00', '2026-04-02 12:00:00'), "
        "(11, 'decision', 'd1', 1, "
        " '2026-04-03 12:00:00', '2026-04-03 12:00:00');"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, NEW_HEAD)

    conn = sqlite3.connect(str(scratch_db))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM task_state ORDER BY task_id"
    ).fetchall()
    assert len(rows) == 2

    t1 = rows[0]
    assert t1["task_id"] == 1
    assert t1["note_count"] == 2
    assert t1["decision_count"] == 1
    assert t1["last_status_change_at"] is None
    assert t1["last_note_at"] == "2026-04-03 12:00:00"

    t2 = rows[1]
    assert t2["task_id"] == 2
    assert t2["note_count"] == 0
    assert t2["decision_count"] == 0
    assert t2["last_note_at"] is None
    assert t2["last_touched_at"] == "2026-04-05 10:00:00"

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(note)").fetchall()}
    assert "mental_model" in cols

    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(wizardsession)"
    ).fetchall()}
    assert "session_state" in cols

    conn.close()


def test_downgrade_removes_table_and_columns(scratch_db, tmp_path):
    cfg = _alembic_config(scratch_db)
    command.upgrade(cfg, NEW_HEAD)
    command.downgrade(cfg, PREVIOUS_HEAD)

    conn = sqlite3.connect(str(scratch_db))
    conn.row_factory = sqlite3.Row

    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "task_state" not in tables

    note_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(note)"
    ).fetchall()}
    assert "mental_model" not in note_cols

    sess_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(wizardsession)"
    ).fetchall()}
    assert "session_state" not in sess_cols

    conn.close()
