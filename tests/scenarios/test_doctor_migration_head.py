"""Scenario: doctor reported "Migration current — PASS" on a database whose
migrations were provably broken.

The check read the stamped revision out of alembic_version and returned it as the
success message without ever comparing it to the head revision. Any stamp at all
passed, so a database sitting several revisions behind — or wedged mid-migration —
looked healthy in a 10/10 green report. That is worse than no check: it actively
argues against the thing that is wrong.
"""

import sqlite3

from wizard.cli.doctor import _check_migration_current


def _stamp(db_path, revision: str | None) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        if revision is not None:
            conn.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        conn.commit()


def _head() -> str:
    import importlib.resources

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option(
        "script_location", str(importlib.resources.files("wizard").joinpath("alembic"))
    )
    return ScriptDirectory.from_config(cfg).get_current_head()


def test_passes_when_database_is_at_head(tmp_path, monkeypatch):
    db = tmp_path / "wizard.db"
    _stamp(db, _head())
    monkeypatch.setattr("wizard.cli.doctor.settings.db", str(db))
    monkeypatch.delenv("WIZARD_DB", raising=False)

    passed, message = _check_migration_current()
    assert passed, message


def test_fails_when_migrations_are_pending(tmp_path, monkeypatch):
    """The exact false PASS: a real revision, but not head."""
    db = tmp_path / "wizard.db"
    _stamp(db, "b8908e3438a3")
    monkeypatch.setattr("wizard.cli.doctor.settings.db", str(db))
    monkeypatch.delenv("WIZARD_DB", raising=False)

    passed, message = _check_migration_current()
    assert not passed
    assert "b8908e3438a3" in message
    assert _head() in message
    assert "wizard migrate" in message


def test_fails_when_database_has_never_been_stamped(tmp_path, monkeypatch):
    db = tmp_path / "wizard.db"
    _stamp(db, None)
    monkeypatch.setattr("wizard.cli.doctor.settings.db", str(db))
    monkeypatch.delenv("WIZARD_DB", raising=False)

    passed, message = _check_migration_current()
    assert not passed
