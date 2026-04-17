import datetime
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from wizard import agent_registration
from wizard.cli import analytics as analytics_module
from wizard.cli.configure import (
    configure_jira,
    configure_notion,
    jira_is_configured,
    notion_is_configured,
    run_jira_configure,
    run_notion_discovery,
)
from wizard.cli.doctor import db_is_healthy, doctor
from wizard.config import settings
from wizard.database import get_session as get_db_session
from wizard.deps import get_sync_service

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


def _prompt_integrations(cfg: dict, config_path: Path) -> tuple[str, str]:
    """Run integration selection prompt and configure chosen integrations.

    Returns (notion_status, jira_status).
    """
    typer.echo("\nWhich integrations would you like to configure?")
    typer.echo("  1. Notion")
    typer.echo("  2. Jira")
    typer.echo("  3. Both")
    typer.echo("  4. Neither")
    int_selection = typer.prompt("Enter number (1-4)")
    try:
        int_idx = int(int_selection)
        if int_idx not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        typer.echo("Invalid selection.", err=True)
        raise typer.Exit(1) from None

    wants_notion = int_idx in (1, 3)
    wants_jira = int_idx in (2, 3)

    notion_status = "skipped"
    jira_status = "skipped"

    if wants_notion:
        if notion_is_configured(cfg):
            typer.echo("\nNotion already configured — run 'wizard configure --notion' to update")
            notion_status = "already configured"
        else:
            try:
                configure_notion(cfg, config_path)
                notion_status = "configured"
            except Exception as exc:
                typer.echo(f"\nNotion configuration failed: {exc}", err=True)
                raise typer.Exit(1) from exc

    if wants_jira:
        # Re-read to get the authoritative on-disk state after the Notion step
        with open(config_path) as f:
            cfg.update(json.load(f))
        if jira_is_configured(cfg):
            typer.echo("\nJira already configured — run 'wizard configure --jira' to update")
            jira_status = "already configured"
        else:
            configure_jira(cfg, config_path)
            jira_status = "configured"

    return notion_status, jira_status


def _prompt_and_register_agents(agent: str | None) -> list[str]:
    """Run agent selection prompt (or validate --agent flag) and register.

    Returns list of registered agent IDs.
    """
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
            raise typer.Exit(1) from None

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
    return agents_to_register


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

    notion_status, jira_status = _prompt_integrations(cfg, config_path)

    _ensure_editable_pth()
    _refresh_skills(WIZARD_HOME / "skills")

    _wizard_db_env = os.environ.get("WIZARD_DB")
    db_path = Path(_wizard_db_env) if _wizard_db_env else (WIZARD_HOME / "wizard.db")
    if not db_is_healthy(db_path):
        typer.echo("Initialising database...")
        repo_root = Path(__file__).resolve().parents[3]
        alembic_args = (
            ["uv", "run", "alembic", "upgrade", "head"]
            if shutil.which("uv")
            else [sys.executable, "-m", "alembic", "upgrade", "head"]
        )
        ok, output = _run_update_step("run migrations", alembic_args, repo_root)
        if not ok:
            typer.echo(output, err=True)
            raise typer.Exit(1)

    agents_to_register = _prompt_and_register_agents(agent)

    typer.echo("\n" + "─" * 45)
    typer.echo("Setup complete.")
    typer.echo(f"  Notion  {notion_status}" + (
        "" if notion_status != "skipped" else " (run 'wizard configure --notion' to add)"
    ))
    typer.echo(f"  Jira    {jira_status}" + (
        "" if jira_status != "skipped" else " (run 'wizard configure --jira' to add)"
    ))
    agent_label = ", ".join(agents_to_register)
    typer.echo(f"  Agent   {agent_label}")


@app.command()
def configure(
    notion: bool = typer.Option(False, "--notion", help="Re-run Notion schema discovery"),
    jira: bool = typer.Option(False, "--jira", help="Re-configure Jira credentials"),
) -> None:
    """Configure Wizard integrations."""
    if notion:
        run_notion_discovery(WIZARD_HOME / "config.json")
        return
    if jira:
        run_jira_configure(WIZARD_HOME / "config.json")
        return
    typer.echo("Available flags: --notion, --jira")


@app.command()
def sync() -> None:
    """Run Jira and Notion sync manually (outside a session)."""
    svc = get_sync_service()
    with get_db_session() as session:
        results = svc.sync_all(session)

    for r in results:
        if r.skipped:
            status = "skipped (not configured)"
        elif r.ok:
            status = "ok"
        else:
            status = f"FAILED: {r.error}"
        typer.echo(f"  {r.source}: {status}")

    typer.echo("Sync complete.")


def _confirm_uninstall(
    registered: list[str],
    existing_files: list[tuple[str, str | None]],
    has_wizard_dir: bool,
) -> bool:
    """Print deletion manifest and prompt for confirmation. Returns True if confirmed."""
    typer.echo("This will permanently delete:")
    for name, desc in existing_files:
        suffix = f"  ({desc})" if desc else ""
        typer.echo(f"  ~/.wizard/{name}{suffix}")
    if has_wizard_dir and not existing_files:
        typer.echo("  ~/.wizard/")
    for aid in registered:
        typer.echo(f"  wizard MCP entry for {aid}")
    typer.echo("")
    return typer.confirm("Are you sure?")


def _deregister_agents(registered: list[str]) -> None:
    """Deregister all agents, printing status for each."""
    for aid in registered:
        try:
            agent_registration.deregister(aid)
            typer.echo(f"  Removed wizard MCP from {aid}")
        except Exception as exc:
            typer.echo(f"  Warning: could not deregister {aid}: {exc}", err=True)


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

    if not yes and not _confirm_uninstall(registered, existing_files, has_wizard_dir):
        typer.echo("Aborted.")
        return

    _deregister_agents(registered)

    if has_wizard_dir:
        try:
            shutil.rmtree(WIZARD_HOME)
            typer.echo(f"  Removed {WIZARD_HOME}")
        except OSError as e:
            typer.echo(f"  Failed to remove {WIZARD_HOME}: {e}", err=True)
            raise typer.Exit(code=1) from e

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
            raise typer.Exit(1) from exc
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
