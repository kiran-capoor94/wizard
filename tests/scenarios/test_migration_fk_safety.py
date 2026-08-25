"""Scenario: a batch_alter_table on a table that other tables reference used to
abort the whole migration and leave the database permanently stuck.

`drop_synthesis_columns` runs `batch_alter_table("wizardsession")`. On SQLite that
is a table rebuild: create `_alembic_tmp_wizardsession`, copy rows, DROP the
original, rename the copy. `toolcall.session_id` and `note.session_id` are foreign
keys onto `wizardsession`, and database.py turns on FK enforcement for every
connection, so the DROP aborts with "FOREIGN KEY constraint failed".

The failure is not self-healing: alembic leaves `_alembic_tmp_wizardsession`
behind, so every retry then dies earlier with "table already exists".
"""

import sqlite3

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _seed_parent_child(*, path: str) -> None:
    """A parent table with a doomed column, referenced by a child holding rows."""
    with sqlite3.connect(path) as raw:
        raw.executescript(
            """
            CREATE TABLE parent (id INTEGER PRIMARY KEY, doomed TEXT, keep TEXT);
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER REFERENCES parent(id)
            );
            INSERT INTO parent (id, doomed, keep) VALUES (1, 'x', 'y');
            INSERT INTO child (id, parent_id) VALUES (1, 1);
            """
        )


def _batch_drop_column(engine) -> None:
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations(ctx).batch_alter_table("parent") as batch_op:
            batch_op.drop_column("doomed")


def _engine_with_fk(path: str, *, enforce: bool):
    from sqlalchemy import event

    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _record):  # noqa: ANN202
        cur = dbapi_conn.cursor()
        cur.execute(f"PRAGMA foreign_keys={'ON' if enforce else 'OFF'}")
        cur.close()

    return engine


def test_batch_alter_table_aborts_while_fk_enforcement_is_on(tmp_path):
    """Reproduces the original failure: the rebuild's DROP TABLE hits the FK."""
    db = tmp_path / "wizard.db"
    _seed_parent_child(path=str(db))

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        _batch_drop_column(_engine_with_fk(str(db), enforce=True))


def test_batch_alter_table_succeeds_with_fk_enforcement_off(tmp_path):
    """The fix: migrations connect with foreign_keys=OFF, so the rebuild lands."""
    db = tmp_path / "wizard.db"
    _seed_parent_child(path=str(db))

    _batch_drop_column(_engine_with_fk(str(db), enforce=False))

    with sqlite3.connect(str(db)) as raw:
        cols = {r[1] for r in raw.execute("PRAGMA table_info(parent)")}
        assert "doomed" not in cols
        assert "keep" in cols
        # The child row survives; the FK target still exists.
        assert raw.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 1
        assert raw.execute("PRAGMA foreign_key_check").fetchall() == []


def test_connect_pragma_disables_fks_only_during_migrations(monkeypatch):
    """`foreign_keys` is a no-op inside a transaction, so it has to be set as the
    connection is handed out. Exercises the real listener on a throwaway
    connection — the suite's shared in-memory engine must not be touched."""
    from wizard import database

    raw = sqlite3.connect(":memory:")

    monkeypatch.setattr(database, "_MIGRATIONS_RUNNING", True)
    database._set_sqlite_pragmas(raw, None)
    assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 0

    monkeypatch.setattr(database, "_MIGRATIONS_RUNNING", False)
    database._set_sqlite_pragmas(raw, None)
    assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    raw.close()


def test_migration_mode_sets_and_clears_the_flag(monkeypatch):
    """env.py wraps every alembic run in this, so all entry points are covered:
    `wizard migrate`, `wizard update`, and a bare `alembic upgrade head`."""
    from wizard import database

    monkeypatch.setattr(database, "_drop_stale_batch_tables", lambda: None)

    with database.migration_mode():
        assert database._MIGRATIONS_RUNNING is True
    assert database._MIGRATIONS_RUNNING is False


def test_migration_mode_clears_the_flag_when_the_migration_raises(monkeypatch):
    from wizard import database

    monkeypatch.setattr(database, "_drop_stale_batch_tables", lambda: None)

    with pytest.raises(RuntimeError), database.migration_mode():
        raise RuntimeError("migration blew up")

    assert database._MIGRATIONS_RUNNING is False


def test_migration_mode_never_disposes_an_in_memory_engine(monkeypatch):
    """Disposing an in-memory engine discards the schema that was just migrated —
    which is exactly how tests/conftest.py builds the suite's schema."""
    from wizard import database

    monkeypatch.setattr(database, "_drop_stale_batch_tables", lambda: None)
    monkeypatch.setattr(database, "_is_in_memory", lambda: True)
    disposals: list[int] = []
    monkeypatch.setattr(database.engine, "dispose", lambda: disposals.append(1))

    with database.migration_mode():
        pass

    assert disposals == []


def test_migration_mode_disposes_a_file_backed_engine(monkeypatch):
    """File-backed pools do hand back pre-flag connections, so they must be dropped."""
    from wizard import database

    monkeypatch.setattr(database, "_drop_stale_batch_tables", lambda: None)
    monkeypatch.setattr(database, "_is_in_memory", lambda: False)
    disposals: list[int] = []
    monkeypatch.setattr(database.engine, "dispose", lambda: disposals.append(1))

    with database.migration_mode():
        pass

    assert len(disposals) == 2, "dispose before handing connections to alembic, and after"


def test_migration_mode_clears_stale_batch_tables_before_running(monkeypatch):
    """The wedge only clears if cleanup happens before alembic touches the schema."""
    from wizard import database

    calls: list[str] = []
    monkeypatch.setattr(database, "_drop_stale_batch_tables", lambda: calls.append("cleanup"))

    with database.migration_mode():
        calls.append("upgrade")

    assert calls == ["cleanup", "upgrade"]


def test_stale_batch_tables_are_dropped(tmp_path, monkeypatch):
    """A half-finished batch migration must not wedge every future upgrade."""
    from wizard import database

    db = tmp_path / "wizard.db"
    with sqlite3.connect(str(db)) as raw:
        raw.executescript(
            """
            CREATE TABLE _alembic_tmp_wizardsession (id INTEGER PRIMARY KEY);
            CREATE TABLE _alembic_tmp_note (id INTEGER PRIMARY KEY);
            CREATE TABLE wizardsession (id INTEGER PRIMARY KEY);
            """
        )

    engine = create_engine(f"sqlite:///{db}")
    monkeypatch.setattr(database, "engine", engine)
    database._drop_stale_batch_tables()

    with engine.connect() as conn:
        remaining = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert not any(n.startswith("_alembic_tmp_") for n in remaining)
    assert "wizardsession" in remaining, "real tables must be left alone"


def test_drop_stale_batch_tables_is_a_noop_on_a_clean_db(tmp_path, monkeypatch):
    from wizard import database

    db = tmp_path / "wizard.db"
    with sqlite3.connect(str(db)) as raw:
        raw.execute("CREATE TABLE note (id INTEGER PRIMARY KEY)")

    engine = create_engine(f"sqlite:///{db}")
    monkeypatch.setattr(database, "engine", engine)
    database._drop_stale_batch_tables()

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE name='note'")
        ).scalar() == 1
