"""Vacuum logic for wizard vacuum."""

from __future__ import annotations

import os
import sqlite3 as _sqlite3
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

try:
    import sqlite_vec as _sqlite_vec
except ImportError:
    _sqlite_vec = None  # type: ignore[assignment]

from wizard.config import settings

_console = Console()


def run_vacuum() -> None:
    """Clear synthesised transcript blobs, orphaned embeddings, and compact the database."""
    db_path = Path(os.environ.get("WIZARD_DB", settings.db))
    if not db_path.exists():
        rprint("[red]Database not found.[/red] Run [bold]wizard setup[/bold] first.")
        raise typer.Exit(1)

    size_before = db_path.stat().st_size
    with (
        _console.status("Vacuuming database..."),
        _sqlite3.connect(str(db_path)) as conn,
    ):
        cur = conn.execute(
            "UPDATE wizardsession SET transcript_raw = NULL"
            " WHERE is_synthesised = 1 AND synthesis_status = 'complete'"
            " AND transcript_raw IS NOT NULL"
        )
        cleared = cur.rowcount
        orphaned = 0
        try:
            if _sqlite_vec is not None:
                conn.enable_load_extension(True)
                _sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            orphan_cur = conn.execute(
                "DELETE FROM vec_note_embeddings"
                " WHERE note_id NOT IN (SELECT id FROM note)"
            )
            orphaned = orphan_cur.rowcount
        except Exception:
            pass
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.execute("VACUUM")

    size_after = db_path.stat().st_size
    mb_before = size_before / 1_048_576
    mb_after = size_after / 1_048_576
    rprint(Panel(
        f"  [green]✓[/green]  Cleared [bold]{cleared}[/bold] transcript blob(s)\n"
        f"  [green]✓[/green]  Removed [bold]{orphaned}[/bold] orphaned embedding(s)\n"
        f"  [green]✓[/green]  Database: [dim]{mb_before:.1f} MB[/dim]"
        f" → [bold]{mb_after:.1f} MB[/bold]"
        f" ([green]freed {mb_before - mb_after:.1f} MB[/green])",
        title="[green]Vacuum complete[/green]",
        border_style="green",
    ))
