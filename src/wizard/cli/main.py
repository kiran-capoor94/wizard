import json
import logging
import shutil
from pathlib import Path
from typing import Optional

import typer

from wizard import agent_registration

logger = logging.getLogger(__name__)

app = typer.Typer(name="wizard", invoke_without_command=True)


@app.callback()
def _main_callback() -> None:
    """Wizard — local memory layer for AI agents."""


WIZARD_HOME = Path.home() / ".wizard"

_DEFAULT_CONFIG = {
    "jira": {"base_url": "", "project_key": "", "token": "", "email": ""},
    "notion": {"token": "", "daily_page_id": "", "sisu_work_page_id": "", "tasks_db_id": "", "meetings_db_id": ""},
    "scrubbing": {"enabled": True, "allowlist": []},
}


def _package_skills_dir() -> Path:
    """Resolve the skills directory shipped inside the wizard package."""
    return Path(__file__).resolve().parent.parent / "skills"


_AGENT_CHOICES = ["claude-code", "claude-desktop", "gemini", "opencode", "codex", "all"]


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

    # Copy skills from package to ~/.wizard/skills/
    source = _package_skills_dir()
    dest = WIZARD_HOME / "skills"
    if source.exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        typer.echo(f"Installed skills to {dest}")
    else:
        typer.echo("No skills found in package — skipping skill install")

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


@app.command()
def doctor() -> None:
    """Check wizard installation health."""
    ok = True

    try:
        from wizard.config import settings
    except Exception as e:
        typer.echo(f"  [ERROR] config failed to load: {e}")
        typer.echo("\nSome checks failed — run 'wizard setup' to fix.")
        raise typer.Exit(code=1)

    # 1. Check ~/.wizard/ exists
    if WIZARD_HOME.exists():
        typer.echo(f"  [ok] wizard home: {WIZARD_HOME}")
    else:
        typer.echo(f"  [MISSING] wizard home not found: {WIZARD_HOME}")
        ok = False

    # 2. Check config.json
    config_path = WIZARD_HOME / "config.json"
    if config_path.exists():
        typer.echo(f"  [ok] config: {config_path}")
    else:
        typer.echo(f"  [MISSING] config not found: {config_path}")
        ok = False

    # 3. Check DB
    db_path = Path(settings.db)
    if settings.db == ":memory:" or db_path.exists():
        typer.echo(f"  [ok] database: {settings.db}")
    else:
        typer.echo(f"  [MISSING] database not found: {settings.db}")
        ok = False

    # 4. Check integrations
    if settings.jira.token:
        typer.echo("  [ok] jira: configured")
    else:
        typer.echo("  [--] jira: not configured")

    if settings.notion.token:
        typer.echo("  [ok] notion: configured")
    else:
        typer.echo("  [--] notion: not configured")

    # 5. Check skills
    skills_dir = WIZARD_HOME / "skills"
    if skills_dir.exists() and any(skills_dir.iterdir()):
        skill_count = sum(1 for d in skills_dir.iterdir() if d.is_dir())
        typer.echo(f"  [ok] skills: {skill_count} installed")
    else:
        typer.echo("  [MISSING] skills not installed — run 'wizard setup'")
        ok = False

    if ok:
        typer.echo("\nAll checks passed.")
    else:
        typer.echo("\nSome checks failed — run 'wizard setup' to fix.")
        raise typer.Exit(code=1)


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
