"""Verify vec_note_embeddings virtual table is created at startup."""
from sqlalchemy import text

from wizard.database import create_vec_tables, engine


def test_vec_table_exists():
    create_vec_tables()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'vec_%'")
        ).fetchall()
    names = [r[0] for r in rows]
    assert any("vec_note_embeddings" in n for n in names), f"vec table not found, got: {names}"
