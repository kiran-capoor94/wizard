import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from wizard import agent_registration
from wizard import notion_discovery  # for --reconfigure-notion; enables patching
from notion_client import Client as NotionSdkClient  # for --reconfigure-notion; enables patching
from wizard.cli import analytics as analytics_module  # enables patching
from wizard.database import get_session as get_db_session  # enables patching

logger = logging.getLogger(__name__)

app = typer.Typer(name="wizard", invoke_without_command=True)


@app.callback()
def _main_callback() -> None:
    """Wizard — local memory layer for AI agents."""


WIZARD_HOME = Path.home() / ".wizard"

_DEFAULT_CONFIG = {
    "jira": {"base_url": "", "project_key": "", "token": "", "email": ""},
    "notion": {"token": "", "sisu_work_page_id": "", "tasks_db_id": "", "meetings_db_id": ""},
    "scrubbing": {"enabled": True, "allowlist": []},
}


def _package_skills_dir() -> Path:
    """Resolve the skills directory shipped inside the wizard package."""
    return Path(__file__).resolve().parent.parent / "skills"


_AGENT_CHOICES = ["claude-code", "claude-desktop", "gemini", "opencode", "codex", "all"]


def _run_notion_discovery(config_path: Path) -> None:
    from wizard.integrations import ConfigurationError

    if not config_path.exists():
        typer.echo("Config not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)

    with open(config_path) as f:
        cfg = json.load(f)

    notion_cfg = cfg.get("notion", {})
    token = notion_cfg.get("token", "")
    tasks_db_id = notion_cfg.get("tasks_db_id", "")
    meetings_db_id = notion_cfg.get("meetings_db_id", "")

    if not token:
        typer.echo("No Notion token configured. Set notion.token in config.json first.", err=True)
        raise typer.Exit(1)

    client = NotionSdkClient(auth=token)
    typer.echo("Fetching Notion database schemas...")

    tasks_props = notion_discovery.fetch_db_properties(client, tasks_db_id)
    meetings_props = notion_discovery.fetch_db_properties(client, meetings_db_id)
    all_props = {**tasks_props, **meetings_props}

    required_fields = ["task_name", "task_status", "meeting_title"]
    all_fields = [
        "task_name", "task_status", "task_priority", "task_due_date", "task_jira_key",
        "meeting_title", "meeting_date", "meeting_url", "meeting_summary",
    ]

    matches = notion_discovery.match_properties(all_props, all_fields)

    for field in required_fields:
        if matches[field] is None:
            available_names = list(all_props.keys())
            typer.echo(f"Could not auto-match required field '{field}'.")
            typer.echo(f"Available properties: {', '.join(available_names)}")
            value = typer.prompt(f"Enter Notion property name for '{field}' (or press Enter to skip)")
            if not value:
                raise ConfigurationError(f"Required field '{field}' must be mapped.")
            matches[field] = value

    schema = {k: v for k, v in matches.items() if v is not None}
    cfg.setdefault("notion", {})["notion_schema"] = schema
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    typer.echo("Notion schema updated:")
    for k, v in schema.items():
        typer.echo(f"  {k}: {v}")


def _refresh_skills(dest: Path) -> None:
    """Copy skills from the package into dest, replacing any existing copy."""
    source = _package_skills_dir()
    if source.exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        typer.echo(f"Installed skills to {dest}")
    else:
        typer.echo("No skills found in package — skipping skill install")


def _run_update_step(label: str, args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run a subprocess step, printing label and ok/FAILED. Returns (success, output)."""
    typer.echo(f"  {label}...", nl=False)
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    ok = result.returncode == 0
    typer.echo(" ok" if ok else " FAILED")
    return ok, (result.stdout + result.stderr).strip()


@app.command()
def setup(
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent to register: claude-code, claude-desktop, gemini, opencode, codex, all",
    ),
    reconfigure_notion: bool = typer.Option(
        False, "--reconfigure-notion",
        help="Re-run Notion schema discovery only",
    ),
) -> None:
    """Create ~/.wizard, default config, install skills, and register MCP."""
    if reconfigure_notion:
        _run_notion_discovery(WIZARD_HOME / "config.json")
        return

    WIZARD_HOME.mkdir(parents=True, exist_ok=True)

    config_path = WIZARD_HOME / "config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(_DEFAULT_CONFIG, indent=2))
        typer.echo(f"Created default config at {config_path}")
    else:
        typer.echo(f"Config already exists at {config_path}")

    # Copy skills from package to ~/.wizard/skills/
    _refresh_skills(WIZARD_HOME / "skills")

    # Determine which agent(s) to register
    if agent is None:
        typer.echo("Which agent would you like to register?")
        for i, choice in enumerate(_AGENT_CHOICES, 1):
            typer.echo(f"  {i}. {choice}")
        selection = typer.prompt(f"Enter number (1-{len(_AGENT_CHOICES)})")
        try:
            idx = int(selection) - 1
            agent = _AGENT_CHOICES[idx]
        except (ValueError, IndexError):
            typer.echo("Invalid selection.", err=True)
            raise typer.Exit(1)

    if agent == "all":
        agents_to_register = [a for a in _AGENT_CHOICES if a != "all"]
    elif agent not in [a for a in _AGENT_CHOICES if a != "all"]:
        typer.echo(f"Unknown agent: {agent}", err=True)
        raise typer.Exit(1)
    else:
        agents_to_register = [agent]

    for aid in agents_to_register:
        try:
            agent_registration.register(aid)
            typer.echo(f"  Registered {aid}")
        except Exception as exc:
            typer.echo(f"  Warning: could not register {aid}: {exc}", err=True)

    agent_registration.write_registered_agents(agents_to_register)

    typer.echo("Setup complete.")


@app.command()
def sync() -> None:
    """Run Jira and Notion sync manually (outside a session)."""
    from wizard.database import get_session
    from wizard.deps import sync_service

    svc = sync_service()
    with get_session() as session:
        results = svc.sync_all(session)

    for r in results:
        status = "ok" if r.ok else f"FAILED: {r.error}"
        typer.echo(f"  {r.source}: {status}")

    typer.echo("Sync complete.")


# --- doctor helpers ---


def _check_db_file() -> tuple[bool, str]:
    import os
    from wizard.config import settings
    db_path_str = os.environ.get("WIZARD_DB", settings.db)
    db_path = Path(db_path_str)
    if db_path.exists():
        return True, f"Database found: {db_path}"
    return False, f"Database not found: {db_path} — run 'wizard setup' first"


def _check_db_tables() -> tuple[bool, str]:
    import os
    import sqlite3
    from wizard.config import settings
    db_path_str = os.environ.get("WIZARD_DB", settings.db)
    db_path = Path(db_path_str)
    if not db_path.exists():
        return False, "Database file missing — cannot check tables"
    try:
        conn = sqlite3.connect(str(db_path))
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        required = {"task", "note", "meeting", "wizardsession", "toolcall"}
        missing = required - tables
        if missing:
            return False, f"Missing tables: {missing}"
        return True, "All required tables present"
    except Exception as exc:
        return False, f"Could not inspect tables: {exc}"


def _check_config_file() -> tuple[bool, str]:
    import os
    config_path = Path(os.environ.get("WIZARD_CONFIG_FILE", str(Path.home() / ".wizard" / "config.json")))
    if config_path.exists():
        return True, f"Config file found: {config_path}"
    return False, f"Config file not found: {config_path}"


def _check_notion_token() -> tuple[bool, str]:
    from wizard.config import Settings
    s = Settings()
    if s.notion.token:
        return True, "Notion token configured"
    return False, "Notion token not set (notion.token)"


def _check_jira_token() -> tuple[bool, str]:
    from wizard.config import Settings
    s = Settings()
    if s.jira.token:
        return True, "Jira token configured"
    return False, "Jira token not set (jira.token) — Jira sync disabled"


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
        import os
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine
        from wizard.config import settings
        db_path_str = os.environ.get("WIZARD_DB", settings.db)
        engine = create_engine(f"sqlite:///{db_path_str}")
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
        return True, f"Migration current: {current}"
    except Exception as exc:
        return False, f"Migration check failed: {exc}"


def _check_skills_installed() -> tuple[bool, str]:
    skills_dir = Path.home() / ".wizard" / "skills"
    if skills_dir.exists() and any(skills_dir.iterdir()):
        return True, f"Skills directory present: {skills_dir}"
    return False, f"Skills not installed at {skills_dir} — run 'wizard setup --agent claude-code'"


def _validate_properties(
    available: dict[str, str], expected: list[tuple[str, str]]
) -> list[str]:
    """Return error strings for each property that is missing or has the wrong type."""
    errors = []
    for name, expected_type in expected:
        if name not in available:
            errors.append(f"'{name}' not found (expected {expected_type})")
        elif available[name] != expected_type:
            errors.append(f"'{name}' is {available[name]}, expected {expected_type}")
    return errors


def _check_notion_schema() -> tuple[bool, str]:
    from wizard.config import Settings
    from wizard.integrations import NotionSdkClient
    from wizard import notion_discovery

    s = Settings()
    notion = s.notion
    schema = notion.notion_schema

    if not notion.token or not notion.tasks_db_id or not notion.meetings_db_id:
        return False, "Notion not configured — run 'wizard setup --reconfigure-notion'"

    client = NotionSdkClient(auth=notion.token)
    tasks_props = notion_discovery.fetch_db_properties(client, notion.tasks_db_id)
    meetings_props = notion_discovery.fetch_db_properties(client, notion.meetings_db_id)

    if not tasks_props and not meetings_props:
        return False, "Could not reach Notion API — check token and network"

    task_fields: list[tuple[str, str]] = [
        (schema.task_name, "title"),
        (schema.task_status, "status"),
        (schema.task_priority, "select"),
        (schema.task_due_date, "date"),
        (schema.task_jira_key, "url"),
    ]
    meeting_fields: list[tuple[str, str]] = [
        (schema.meeting_title, "title"),
        (schema.meeting_date, "date"),
        (schema.meeting_url, "url"),
        (schema.meeting_summary, "rich_text"),
        ("Category", "multi_select"),
    ]

    task_errors = _validate_properties(tasks_props, task_fields)
    meeting_errors = _validate_properties(meetings_props, meeting_fields)

    parts = []
    if task_errors:
        parts.append(f"Tasks DB: {'; '.join(task_errors)}")
    if meeting_errors:
        parts.append(f"Meetings DB: {'; '.join(meeting_errors)}")

    if parts:
        return False, " | ".join(parts)
    return True, "Notion schema matches live DB"


_DOCTOR_CHECK_NAMES = [
    ("DB file exists", "_check_db_file"),
    ("Notion token", "_check_notion_token"),
    ("Jira token", "_check_jira_token"),
    ("Config file", "_check_config_file"),
    ("DB tables", "_check_db_tables"),
    ("Allowlist file", "_check_allowlist_file"),
    ("Agent registered", "_check_agent_registrations"),
    ("Notion schema", "_check_notion_schema"),
    ("Migration current", "_check_migration_current"),
    ("Skills installed", "_check_skills_installed"),
]


def _get_doctor_checks():
    """Build doctor checks list at call time so individual checks can be patched in tests."""
    import wizard.cli.main as _self
    return [(name, getattr(_self, fn_name)) for name, fn_name in _DOCTOR_CHECK_NAMES]


@app.command()
def doctor(
    all_checks: bool = typer.Option(False, "--all", help="Report all failures instead of stopping at first"),
) -> None:
    """Run health checks on the wizard installation."""
    failures = []
    notion_token_ok = True

    for i, (name, check_fn) in enumerate(_get_doctor_checks(), 1):
        if i == 8 and not notion_token_ok:
            typer.echo(f"  [{i:2d}] SKIP  {name} (Notion token not configured)")
            continue

        passed, message = check_fn()

        if i == 2:
            notion_token_ok = passed

        status = "PASS" if passed else "FAIL"
        typer.echo(f"  [{i:2d}] {status}  {name}: {message}")

        if not passed:
            failures.append((i, name, message))
            if not all_checks:
                raise typer.Exit(1)

    if failures:
        raise typer.Exit(1)
    typer.echo("All checks passed.")


@app.command()
def uninstall(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
) -> None:
    """Remove all Wizard runtime state and MCP registration."""
    # Read which agents are registered
    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()

    # Gather which wizard files exist
    wizard_files = {
        "wizard.db": "all notes, sessions, meetings",
        "config.json": None,
        "skills/": None,
    }
    existing_files: list[tuple[str, str | None]] = []
    for name, desc in wizard_files.items():
        path = WIZARD_HOME / name.rstrip("/")
        if path.exists():
            existing_files.append((name, desc))

    has_wizard_dir = WIZARD_HOME.exists()
    has_anything = has_wizard_dir or bool(registered)

    if not has_anything:
        typer.echo("Nothing to uninstall.")
        return

    # Confirmation
    if not yes:
        typer.echo("This will permanently delete:")
        for name, desc in existing_files:
            suffix = f"  ({desc})" if desc else ""
            typer.echo(f"  ~/.wizard/{name}{suffix}")
        if has_wizard_dir and not existing_files:
            typer.echo("  ~/.wizard/")
        for aid in registered:
            typer.echo(f"  wizard MCP entry for {aid}")
        typer.echo("")
        confirm = typer.prompt("Are you sure? [y/N]", default="N", show_default=False)
        if confirm.lower() != "y":
            typer.echo("Aborted.")
            return

    # Deregister all agents
    for aid in registered:
        try:
            agent_registration.deregister(aid)
            typer.echo(f"  Removed wizard MCP from {aid}")
        except Exception as exc:
            typer.echo(f"  Warning: could not deregister {aid}: {exc}", err=True)

    # Remove wizard directory
    if has_wizard_dir:
        try:
            shutil.rmtree(WIZARD_HOME)
            typer.echo(f"  Removed {WIZARD_HOME}")
        except OSError as e:
            typer.echo(f"  Failed to remove {WIZARD_HOME}: {e}", err=True)
            raise typer.Exit(code=1)

    typer.echo("Wizard uninstalled. Run `uv pip uninstall wizard` to remove the package.")


@app.command()
def analytics(
    day: bool = typer.Option(False, "--day", help="Show today's analytics"),
    week: bool = typer.Option(False, "--week", help="Show last 7 days (default)"),
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date YYYY-MM-DD"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """Show wizard usage analytics."""
    import datetime
    import os
    from wizard.config import settings

    today = datetime.date.today()

    options_set = sum([day, week, bool(from_date or to_date)])
    if options_set > 1:
        typer.echo("Options --day, --week, --from/--to are mutually exclusive.", err=True)
        raise typer.Exit(1)

    if day:
        start = today
        end = today
    elif from_date or to_date:
        try:
            start = datetime.date.fromisoformat(from_date) if from_date else today - datetime.timedelta(days=7)
            end = datetime.date.fromisoformat(to_date) if to_date else today
        except ValueError as exc:
            typer.echo(f"Invalid date format: {exc}", err=True)
            raise typer.Exit(1)
    else:
        start = today - datetime.timedelta(days=7)
        end = today

    db_path = Path(os.environ.get("WIZARD_DB", settings.db))
    if not db_path.exists():
        typer.echo("Database not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)

    with get_db_session() as db:
        sessions_data = analytics_module.query_sessions(db, start, end)
        notes_data = analytics_module.query_notes(db, start, end)
        tasks_data = analytics_module.query_tasks(db, start, end)
        compounding = analytics_module.query_compounding(db, start, end)

    combined = {
        "sessions": sessions_data,
        "notes": notes_data,
        "tasks": tasks_data,
        "compounding": compounding,
    }
    typer.echo(analytics_module.format_table(combined, start, end))


@app.command()
def update() -> None:
    """Pull latest code, sync deps, run migrations, and refresh skills."""
    repo_root = Path(__file__).resolve().parents[3]
    sync_args = ["uv", "sync"] if shutil.which("uv") else [sys.executable, "-m", "pip", "install", "-e", str(repo_root)]

    steps: list[tuple[str, list[str]]] = [
        ("git pull", ["git", "pull"]),
        ("sync deps", sync_args),
        ("run migrations", ["alembic", "upgrade", "head"]),
    ]

    for label, args in steps:
        ok, output = _run_update_step(label, args, repo_root)
        if not ok:
            typer.echo(output, err=True)
            raise typer.Exit(1)

    _refresh_skills(WIZARD_HOME / "skills")
    typer.echo("Wizard updated.")
