import datetime
import importlib.metadata as importlib_metadata
import importlib.resources
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from wizard import agent_registration
from wizard.cli import analytics as analytics_module
from wizard.cli.capture import capture
from wizard.cli.configure import synthesis_app
from wizard.cli.doctor import db_is_healthy, doctor
from wizard.cli.verify import verify
from wizard.config import settings
from wizard.database import get_session as get_db_session
from wizard.services import RegistrationService

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="wizard",
    invoke_without_command=True,
    help="Wizard — local memory layer for AI agents.",
)

app.command()(doctor)
app.command()(capture)
app.command()(verify)

configure_app = typer.Typer(help="Configure wizard settings.")
app.add_typer(configure_app, name="configure")

_reg_service = RegistrationService(settings)

_AGENT_CHOICES = [
    "claude-code",
    "claude-desktop",
    "gemini",
    "opencode",
    "codex",
    "copilot",
    "all",
]

def is_editable_install() -> bool:
    """True for editable (dev); False for `uv tool install`."""
    try:
        dist = importlib_metadata.distribution("wizard")
        url_json = dist.read_text("direct_url.json")
        if not url_json:
            return True
        data = json.loads(url_json)
        return bool(data.get("editable") or data.get("dir_info", {}).get("editable"))
    except Exception:
        return True


def _run_update_step(label: str, args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run a subprocess step, printing label and ok/FAILED. Returns (success, output)."""
    typer.echo(f"  {label}...", nl=False)
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    ok = result.returncode == 0
    status = (
        typer.style(" ok", fg=typer.colors.GREEN)
        if ok
        else typer.style(" FAILED", fg=typer.colors.RED, bold=True)
    )
    typer.echo(status)
    return ok, (result.stdout + result.stderr).strip()


def _display_agent_registration(results: list[dict]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2)
    table.add_column(min_width=16)
    table.add_column(style="dim")

    for res in results:
        status = "[green]✓[/green]" if res["success"] else "[red]✗[/red]"
        desc = " + ".join(res["parts"]) if res["success"] else res["error"]
        table.add_row(status, res["id"], desc)
    rprint(table)


def _prompt_and_register_agents(agent: str | None) -> list[str]:
    if agent is None:
        agent = typer.prompt(
            "Agent to register",
            type=click.Choice(_AGENT_CHOICES, case_sensitive=False),
            default="claude-code",
        )

    selected: str = str(agent)
    agents_to_register: list[str] = (
        [a for a in _AGENT_CHOICES if a != "all"] if selected == "all" else [selected]
    )

    results = _reg_service.register_agents(agents_to_register)
    _display_agent_registration(results)

    registered = [r["id"] for r in results if r["success"]]
    agent_registration.write_registered_agents(registered)
    return registered


@app.command()
def setup(
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        help="Agent to register: claude-code, claude-desktop, gemini, opencode, codex, all",
    ),
) -> None:
    """Create ~/.wizard, default config, install skills, and register MCP."""
    _reg_service.ensure_wizard_home()
    typer.echo(_reg_service.initialize_config())
    typer.echo(_reg_service.initialize_allowlist())

    _reg_service.ensure_editable_pth()
    agent_registration.refresh_hooks()
    typer.echo(_reg_service.refresh_skills())

    _wizard_db_env = os.environ.get("WIZARD_DB")
    db_path = Path(_wizard_db_env) if _wizard_db_env else (_reg_service.WIZARD_HOME / "wizard.db")
    if not db_is_healthy(db_path):
        from wizard.database import run_migrations
        typer.echo("Initialising database...")
        try:
            run_migrations()
        except Exception as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc

    agents_to_register = _prompt_and_register_agents(agent)

    agent_line = (
        f"  ✅  [bold]{', '.join(agents_to_register)}[/bold] registered\n"
        if agents_to_register
        else ""
    )
    rprint(Panel(
        "  ✅  Installed\n"
        f"{agent_line}"
        "\n"
        "  Next steps:\n"
        "    1. Run [bold]wizard verify[/bold] to confirm MCP is working.\n"
        "    2. Open your agent — the wizard: tools are available automatically.\n"
        "    3. The SessionStart hook calls wizard:session_start for you.\n"
        "\n"
        "  Optionally: [dim]wizard configure knowledge-store[/dim]",
        title="[green]Setup complete[/green]",
        border_style="green",
    ))


@configure_app.command("knowledge-store")
def configure_knowledge_store() -> None:
    """Configure where session summaries are written."""
    config_file = _reg_service.WIZARD_HOME / "config.json"
    existing = json.loads(config_file.read_text()) if config_file.exists() else {}

    raw = typer.prompt(
        "Knowledge store type",
        type=click.Choice(["notion", "obsidian", "none"], case_sensitive=False),
        default="none",
    )
    ks_type = "" if raw == "none" else raw

    ks_config: dict = {"type": ks_type, "notion": {}, "obsidian": {}}

    if ks_type == "notion":
        ks_config["notion"]["daily_parent_id"] = typer.prompt(
            "Notion daily page parent ID", default=""
        )
        ks_config["notion"]["tasks_db_id"] = typer.prompt(
            "Notion tasks DB ID (optional)", default=""
        )
        ks_config["notion"]["meetings_db_id"] = typer.prompt(
            "Notion meetings DB ID (optional)", default=""
        )
    elif ks_type == "obsidian":
        ks_config["obsidian"]["vault_path"] = typer.prompt("Obsidian vault path")
        ks_config["obsidian"]["daily_notes_folder"] = typer.prompt(
            "Daily notes folder", default="Daily"
        )
        ks_config["obsidian"]["tasks_folder"] = typer.prompt(
            "Tasks folder", default="Tasks"
        )

    existing["knowledge_store"] = ks_config
    config_file.write_text(json.dumps(existing, indent=2))
    typer.echo(f"Knowledge store configured: {ks_type or 'none'}")


configure_app.add_typer(synthesis_app, name="synthesis")


def _confirm_uninstall(
    registered: list[str],
    existing_files: list[tuple[str, str | None]],
    has_wizard_dir: bool,
) -> bool:
    """Print deletion manifest and prompt for confirmation. Returns True if confirmed."""
    items: list[str] = []
    for name, desc in existing_files:
        items.append(f"~/.wizard/{name}" + (f"  [dim]({desc})[/dim]" if desc else ""))
    if has_wizard_dir and not existing_files:
        items.append("~/.wizard/")
    for aid in registered:
        items.append(f"wizard MCP entry for [bold]{aid}[/bold]")
    rprint(Panel(
        "\n".join(items), title="[red]This will permanently delete[/red]", border_style="red"
    ))
    return typer.confirm("Are you sure?")


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
        path = _reg_service.WIZARD_HOME / name.rstrip("/")
        if path.exists():
            existing_files.append((name, desc))

    has_wizard_dir = _reg_service.WIZARD_HOME.exists()
    has_anything = has_wizard_dir or bool(registered)

    if not has_anything:
        typer.echo("Nothing to uninstall.")
        return

    if not yes and not _confirm_uninstall(registered, existing_files, has_wizard_dir):
        typer.echo("Aborted.")
        return

    results = _reg_service.deregister_agents(registered)
    _display_agent_registration(results)

    if has_wizard_dir:
        typer.echo(_reg_service.uninstall_wizard())

    typer.echo("Wizard uninstalled. Run `uv pip uninstall wizard` to remove the package.")


@app.command()
def analytics(
    day: bool = typer.Option(False, "--day", help="Show today's analytics"),
    week: bool = typer.Option(False, "--week", help="Show last 7 days (default)"),
    month: bool = typer.Option(False, "--month", help="Show last 30 days"),
    from_date: Optional[str] = typer.Option(
        None, "--from", help="Start date YYYY-MM-DD"
    ),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date YYYY-MM-DD"),
) -> None:
    """Show wizard usage analytics."""
    today = datetime.date.today()

    options_set = sum([day, week, month, bool(from_date or to_date)])
    if options_set > 1:
        typer.echo(
            "Options --day, --week, --month, --year, --from/--to are mutually exclusive.",
            err=True,
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
    elif week:
        start = today - datetime.timedelta(days=7)
        end = today
    elif month:
        start = today - datetime.timedelta(days=30)
        end = today
    else:  # year
        start = today - datetime.timedelta(days=365)
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

    analytics_module.print_analytics(
        {
            "sessions": sessions_data, "notes": notes_data,
            "tasks": tasks_data, "compounding": compounding,
        },
        start, end,
    )


@app.command()
def dashboard() -> None:
    """Launch the Streamlit health dashboard."""
    dashboard_path = str(
        importlib.resources.files("wizard").joinpath("cli").joinpath("dashboard.py")
    )
    streamlit_bin = Path(sys.executable).parent / "streamlit"
    result = subprocess.run(
        [str(streamlit_bin), "run", dashboard_path],
        check=False,
    )
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command()
def update() -> None:
    """Pull latest code (dev) or upgrade tool install, run migrations, re-register agents."""
    from wizard.database import run_migrations

    skills_dest = _reg_service.WIZARD_HOME / "skills"

    if is_editable_install():
        # Dev mode: git pull + uv sync
        repo_root = Path(__file__).resolve().parents[3]
        sync_args = (
            ["uv", "sync"]
            if shutil.which("uv")
            else [sys.executable, "-m", "pip", "install", "-e", str(repo_root)]
        )
        steps = [
            ("git pull", ["git", "pull"]),
            ("sync deps", sync_args),
        ]
        for label, args in steps:
            ok, output = _run_update_step(label, args, repo_root)
            if not ok:
                typer.echo(output, err=True)
                raise typer.Exit(1)
        _reg_service.ensure_editable_pth()
    else:
        # Installed mode: uv tool upgrade
        if not shutil.which("uv"):
            typer.echo("uv not found — cannot upgrade", err=True)
            raise typer.Exit(1)
        ok, output = _run_update_step(
            "upgrade", ["uv", "tool", "upgrade", "wizard"], Path.home()
        )
        if not ok:
            typer.echo(output, err=True)
            raise typer.Exit(1)

    typer.echo("  run migrations... ", nl=False)
    try:
        run_migrations()
        typer.echo("ok")
    except Exception as exc:
        typer.echo(f"FAILED\n{exc}", err=True)
        raise typer.Exit(1) from exc

    agent_registration.refresh_hooks()
    _reg_service.refresh_skills()

    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()

    if registered:
        typer.echo("\nAgents:")
        results = _reg_service.register_agents(registered)
        _display_agent_registration(results)
    else:
        typer.echo("\nNo registered agents found — run: wizard setup --agent <agent>")

    rprint(Panel(
        f"Skills cache: [dim]{skills_dest}[/dim]\n"
        f"Agents updated: [bold]{', '.join(registered) if registered else 'none'}[/bold]",
        title="[green]Wizard updated[/green]",
        border_style="green",
    ))
