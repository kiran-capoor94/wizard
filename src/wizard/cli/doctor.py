import logging
import os
import sqlite3
from pathlib import Path

import typer
from alembic.runtime.migration import MigrationContext
from rich import print as rprint
from rich.table import Table
from sqlalchemy import create_engine

from wizard import agent_registration
from wizard.config import settings

logger = logging.getLogger(__name__)

REQUIRED_TABLES = {"task", "note", "meeting", "wizardsession", "toolcall", "task_state"}


def db_is_healthy(db_path: Path) -> bool:
    """Return True if db_path exists and contains all required tables."""
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(str(db_path)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        return REQUIRED_TABLES.issubset(tables)
    except Exception as e:
        logger.debug("db_is_healthy failed: %s", e)
        return False


def _check_db_file() -> tuple[bool, str]:
    db_path_str = os.environ.get("WIZARD_DB", settings.db)
    db_path = Path(db_path_str)
    if db_path.exists():
        return True, f"Database found: {db_path}"
    return False, f"Database not found: {db_path} — run 'wizard setup' first"


def _check_db_tables() -> tuple[bool, str]:
    db_path_str = os.environ.get("WIZARD_DB", settings.db)
    db_path = Path(db_path_str)
    if not db_path.exists():
        return False, "Database file missing — cannot check tables"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        required = REQUIRED_TABLES
        missing = required - tables
        if missing:
            return False, f"Missing tables: {missing}"
        return True, "All required tables present"
    except Exception as exc:
        return False, f"Could not inspect tables: {exc}"


def _check_config_file() -> tuple[bool, str]:
    config_path = Path(
        os.environ.get(
            "WIZARD_CONFIG_FILE", str(Path.home() / ".wizard" / "config.json")
        )
    )
    if config_path.exists():
        return True, f"Config file found: {config_path}"
    return False, f"Config file not found: {config_path}"


def _check_allowlist_file() -> tuple[bool, str]:
    allowlist = Path.home() / ".wizard" / "allowlist.txt"
    if allowlist.exists():
        return True, f"Allowlist found: {allowlist}"
    return False, f"Allowlist not found: {allowlist}"


def _check_agent_registrations() -> tuple[bool, str]:
    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()
    if registered:
        return True, f"Registered agents: {', '.join(registered)}"
    return False, "No agents registered — run 'wizard setup --agent <agent>'"


def _check_migration_current() -> tuple[bool, str]:
    try:
        db_path_str = os.environ.get("WIZARD_DB", settings.db)
        engine = create_engine(f"sqlite:///{db_path_str}")
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
        return True, f"Migration current: {current}"
    except Exception as exc:
        return False, f"Migration check failed: {exc}"


def _check_skills_installed() -> tuple[bool, str]:
    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()
    for aid in registered:
        skills_dir = agent_registration._AGENT_SKILLS_DIRS.get(aid)
        if skills_dir and skills_dir.exists() and any(skills_dir.iterdir()):
            return True, f"Skills installed for {aid}: {skills_dir}"
    # Fallback: wizard internal cache
    wizard_skills = Path.home() / ".wizard" / "skills"
    if wizard_skills.exists() and any(wizard_skills.iterdir()):
        return True, f"Skills directory present: {wizard_skills}"
    return (
        False,
        "Skills not installed — run 'wizard setup --agent <agent>'",
    )


def _check_knowledge_store() -> tuple[bool, str]:
    ks_type = settings.knowledge_store.type
    if not ks_type:
        msg = (
            "Not configured — session summaries saved locally only. "
            "Run: wizard configure --knowledge-store"
        )
        return True, msg
    return True, f"Configured: {ks_type}"


def run_checks(stop_on_failure: bool = True) -> list[tuple[str, bool, str]]:
    """Run all checks and return list of (name, passed, message) tuples."""
    checks = [
        ("DB file exists", _check_db_file),
        ("Config file", _check_config_file),
        ("DB tables", _check_db_tables),
        ("Allowlist file", _check_allowlist_file),
        ("Agent registered", _check_agent_registrations),
        ("Migration current", _check_migration_current),
        ("Skills installed", _check_skills_installed),
        ("Knowledge store", _check_knowledge_store),
    ]

    results = []
    for name, check_fn in checks:
        passed, message = check_fn()
        results.append((name, passed, message))
        if not passed and stop_on_failure:
            break

    return results


def doctor(
    all_checks: bool = typer.Option(
        False, "--all", help="Report all failures instead of stopping at first"
    ),
) -> None:
    """Run health checks on the wizard installation."""
    results = run_checks(stop_on_failure=not all_checks)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=3)
    table.add_column("Check", min_width=22)
    table.add_column("Status", width=6)
    table.add_column("Details")

    failures = []
    for i, (name, passed, message) in enumerate(results, 1):
        status = "[green]PASS[/green]" if passed else "[bold red]FAIL[/bold red]"
        table.add_row(str(i), name, status, message)
        if not passed:
            failures.append((i, name, message))

    rprint(table)
    if failures:
        raise typer.Exit(1)
    typer.echo("All checks passed.")
