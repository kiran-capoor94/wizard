import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from notion_client import Client as NotionSdkClient

from wizard import agent_registration, notion_discovery
from wizard.cli import analytics as analytics_module
from wizard.cli.doctor import doctor
from wizard.database import get_session as get_db_session

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="wizard",
    invoke_without_command=True,
    help="Wizard — local memory layer for AI agents.",
)

app.command()(doctor)

WIZARD_HOME = Path.home() / ".wizard"

_DEFAULT_CONFIG = {
    "jira": {"base_url": "", "project_key": "", "token": "", "email": ""},
    "notion": {
        "token": "",
        "daily_page_parent_id": "",
        "tasks_ds_id": "",
        "meetings_ds_id": "",
    },
    "scrubbing": {"enabled": True, "allowlist": []},
}

_AGENT_CHOICES = ["claude-code", "claude-desktop", "gemini", "opencode", "codex", "all"]


def _ensure_editable_pth() -> None:
    """Clear the UF_HIDDEN macOS flag from the hatchling editable .pth file.

    uv sets UF_HIDDEN on all .pth files it creates inside .venv. Python 3.14+
    respects UF_HIDDEN and silently skips those files, so the editable install
    silently breaks. os.chflags clears the bit; uv sync does not re-set it on
    files it doesn't need to recreate, so this is persistent across syncs.

    Only needs to be re-run after a full venv rebuild (uv venv / uv pip install -e .).
    """
    import stat

    repo_root = Path(__file__).resolve().parents[3]
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site_packages = repo_root / ".venv" / "lib" / py_ver / "site-packages"
    if not site_packages.exists():
        return

    pth_file = site_packages / "_editable_impl_wizard.pth"
    if not pth_file.exists():
        return

    if not hasattr(os, "chflags"):
        return  # non-macOS — no-op

    st = os.lstat(pth_file)
    if getattr(st, "st_flags", 0) & stat.UF_HIDDEN:
        os.chflags(pth_file, st.st_flags & ~stat.UF_HIDDEN)


def _package_skills_dir() -> Path:
    """Resolve the skills directory shipped inside the wizard package."""
    return Path(__file__).resolve().parent.parent / "skills"


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


def _run_notion_discovery(config_path: Path) -> None:
    from wizard.integrations import ConfigurationError

    if not config_path.exists():
        typer.echo("Config not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)

    with open(config_path) as f:
        cfg = json.load(f)

    notion_cfg = cfg.get("notion", {})
    token = notion_cfg.get("token", "")
    tasks_ds_id = notion_cfg.get("tasks_ds_id", "")
    meetings_ds_id = notion_cfg.get("meetings_ds_id", "")

    if not token:
        typer.echo(
            "No Notion token configured. Set notion.token in config.json first.",
            err=True,
        )
        raise typer.Exit(1)

    client = NotionSdkClient(auth=token)
    typer.echo("Fetching Notion database schemas...")

    tasks_props = notion_discovery.fetch_db_properties(client, tasks_ds_id)
    meetings_props = notion_discovery.fetch_db_properties(client, meetings_ds_id)
    all_props = {**tasks_props, **meetings_props}

    required_fields = ["task_name", "task_status", "meeting_title"]
    all_fields = [
        "task_name",
        "task_status",
        "task_priority",
        "task_due_date",
        "task_jira_key",
        "meeting_title",
        "meeting_category",
        "meeting_date",
        "meeting_url",
        "meeting_summary",
    ]

    matches = notion_discovery.match_properties(all_props, all_fields)

    for field in required_fields:
        if matches[field] is None:
            available_names = list(all_props.keys())
            typer.echo(f"Could not auto-match required field '{field}'.")
            typer.echo(f"Available properties: {', '.join(available_names)}")
            value = typer.prompt(
                f"Enter Notion property name for '{field}' (or press Enter to skip)"
            )
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


@app.command()
def setup(
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent to register: claude-code, claude-desktop, gemini, opencode, codex, all",
    ),
) -> None:
    """Create ~/.wizard, default config, install skills, and register MCP."""
    WIZARD_HOME.mkdir(parents=True, exist_ok=True)

    config_path = WIZARD_HOME / "config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps(_DEFAULT_CONFIG, indent=2))
        typer.echo(f"Created default config at {config_path}")
    else:
        typer.echo(f"Config already exists at {config_path}")

    with open(config_path) as f:
        cfg = json.load(f)

    if not cfg.get("notion", {}).get("daily_page_parent_id"):
        page_id = typer.prompt(
            "Notion daily page parent ID (the page where daily session notes are created)",
            default="",
        )
        if page_id:
            cfg.setdefault("notion", {})["daily_page_parent_id"] = page_id
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=2)
            typer.echo(f"  Set daily_page_parent_id: {page_id}")
        else:
            typer.echo("  Skipped — set notion.daily_page_parent_id in config.json later")

    _ensure_editable_pth()
    _refresh_skills(WIZARD_HOME / "skills")

    if agent is None:
        typer.echo("Which agent would you like to register?")
        for i, choice in enumerate(_AGENT_CHOICES, 1):
            typer.echo(f"  {i}. {choice}")
        selection = typer.prompt(f"Enter number (1-{len(_AGENT_CHOICES)})")
        try:
            idx = int(selection) - 1
            agent = _AGENT_CHOICES[idx]
        except ValueError, IndexError:
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
def configure(
    notion: bool = typer.Option(
        False, "--notion", help="Re-run Notion schema discovery"
    ),
) -> None:
    """Configure Wizard integrations."""
    if notion:
        _run_notion_discovery(WIZARD_HOME / "config.json")
        return
    typer.echo("Available flags: --notion")


@app.command()
def sync() -> None:
    """Run Jira and Notion sync manually (outside a session)."""
    from wizard.database import get_session
    from wizard.deps import get_sync_service

    svc = get_sync_service()
    with get_session() as session:
        results = svc.sync_all(session)

    for r in results:
        status = "ok" if r.ok else f"FAILED: {r.error}"
        typer.echo(f"  {r.source}: {status}")

    typer.echo("Sync complete.")


@app.command()
def uninstall(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
) -> None:
    """Remove all Wizard runtime state and MCP registration."""
    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()

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
        if not typer.confirm("Are you sure?"):
            typer.echo("Aborted.")
            return

    for aid in registered:
        try:
            agent_registration.deregister(aid)
            typer.echo(f"  Removed wizard MCP from {aid}")
        except Exception as exc:
            typer.echo(f"  Warning: could not deregister {aid}: {exc}", err=True)

    if has_wizard_dir:
        try:
            shutil.rmtree(WIZARD_HOME)
            typer.echo(f"  Removed {WIZARD_HOME}")
        except OSError as e:
            typer.echo(f"  Failed to remove {WIZARD_HOME}: {e}", err=True)
            raise typer.Exit(code=1)

    typer.echo(
        "Wizard uninstalled. Run `uv pip uninstall wizard` to remove the package."
    )


@app.command()
def analytics(
    day: bool = typer.Option(False, "--day", help="Show today's analytics"),
    week: bool = typer.Option(False, "--week", help="Show last 7 days (default)"),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date YYYY-MM-DD"
    ),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """Show wizard usage analytics."""
    import datetime
    import os

    from wizard.config import settings

    today = datetime.date.today()

    options_set = sum([day, week, bool(from_date or to_date)])
    if options_set > 1:
        typer.echo(
            "Options --day, --week, --from/--to are mutually exclusive.", err=True
        )
        raise typer.Exit(1)

    if day:
        start = today
        end = today
    elif from_date or to_date:
        try:
            start = (
                datetime.date.fromisoformat(from_date)
                if from_date
                else today - datetime.timedelta(days=7)
            )
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
    sync_args = (
        ["uv", "sync"]
        if shutil.which("uv")
        else [sys.executable, "-m", "pip", "install", "-e", str(repo_root)]
    )
    alembic_args = (
        ["uv", "run", "alembic", "upgrade", "head"]
        if shutil.which("uv")
        else [sys.executable, "-m", "alembic", "upgrade", "head"]
    )

    steps: list[tuple[str, list[str]]] = [
        ("git pull", ["git", "pull"]),
        ("sync deps", sync_args),
        ("run migrations", alembic_args),
    ]

    for label, args in steps:
        ok, output = _run_update_step(label, args, repo_root)
        if not ok:
            typer.echo(output, err=True)
            raise typer.Exit(1)

    _ensure_editable_pth()
    _refresh_skills(WIZARD_HOME / "skills")

    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()
    for aid in registered:
        try:
            agent_registration.register(aid)
            typer.echo(f"  Re-registered {aid}")
        except Exception as exc:
            typer.echo(f"  Warning: could not re-register {aid}: {exc}", err=True)

    typer.echo("Wizard updated.")
