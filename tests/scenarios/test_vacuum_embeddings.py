"""Verify wizard vacuum cleans up orphaned vec_note_embeddings rows."""
import sqlite3


def _make_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE wizardsession (id INTEGER PRIMARY KEY, transcript_raw TEXT)")
        conn.execute("CREATE TABLE note (id INTEGER PRIMARY KEY, content TEXT)")
        conn.execute(
            "CREATE TABLE vec_note_embeddings (note_id INTEGER PRIMARY KEY, embedding BLOB)"
        )
        conn.execute("INSERT INTO note VALUES (1, 'hello')")
        conn.execute("INSERT INTO vec_note_embeddings VALUES (1, x'00')")
        conn.execute("INSERT INTO vec_note_embeddings VALUES (99, x'00')")  # orphan
        conn.commit()


def test_vacuum_removes_orphaned_embeddings(tmp_path, monkeypatch):
    db_path = tmp_path / "wizard.db"
    _make_db(str(db_path))

    monkeypatch.setenv("WIZARD_DB", str(db_path))

    # Patch settings.db so the command resolves to our temp db
    import wizard.config as _cfg
    monkeypatch.setattr(_cfg.settings, "db", str(db_path))

    from typer.testing import CliRunner

    from wizard.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["vacuum"])

    assert result.exit_code == 0, result.output
    assert "1 orphaned" in result.output

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT note_id FROM vec_note_embeddings").fetchall()
    assert [r[0] for r in rows] == [1]
