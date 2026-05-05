"""Embedding backfill logic for wizard compress --backfill."""

from __future__ import annotations

import logging
import os
import sqlite3 as _sqlite3
from pathlib import Path

import typer

try:
    import sqlite_vec as _sqlite_vec
except ImportError:
    _sqlite_vec = None  # type: ignore[assignment]

from wizard.config import settings
from wizard.embedding import embed, serialize_float32

logger = logging.getLogger(__name__)

_BATCH = 50


def run_backfill() -> None:
    """Backfill embeddings for all notes without an entry in vec_note_embeddings."""
    if _sqlite_vec is None:
        typer.echo("sqlite-vec not installed — run: uv add sqlite-vec", err=True)
        raise typer.Exit(1)

    db_path = Path(os.environ.get("WIZARD_DB", settings.db))
    if not db_path.exists():
        typer.echo("Database not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)

    test_vec = embed("test")
    if test_vec is None:
        typer.echo("Embedding model not available.", err=True)
        raise typer.Exit(1)

    with _sqlite3.connect(str(db_path)) as conn:
        conn.enable_load_extension(True)
        _sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        rows = conn.execute(
            "SELECT id, content FROM note "
            "WHERE id NOT IN (SELECT note_id FROM vec_note_embeddings)"
        ).fetchall()
        total = len(rows)
        if total == 0:
            typer.echo("All notes already have embeddings.")
            return

        done = 0
        for i in range(0, total, _BATCH):
            batch = rows[i : i + _BATCH]
            for note_id, content in batch:
                vec = embed(content or "")
                if vec is None:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO vec_note_embeddings(note_id, embedding) VALUES (?, ?)",
                    [note_id, serialize_float32(vec)],
                )
                done += 1
            conn.commit()
            typer.echo(f"Backfilling embeddings: {min(i + _BATCH, total)}/{total}...")

    typer.echo(f"Done. Wrote {done}/{total} embeddings.")
