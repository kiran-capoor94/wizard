"""`wizard update` / `wizard migrate` commands.

Split out of main.py to keep that file under the 500-line cap and to group the
self-upgrade machinery (which has one axis of change: how Wizard upgrades
itself) in one place.
"""

import importlib.metadata as importlib_metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich import print as rprint
from rich.panel import Panel

from wizard import agent_registration
from wizard.database import run_migrations


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


def _run_update_step(label: str, args: list[str], cwd: Path) -> None:
    """Run a subprocess step, printing label and ok/FAILED. Exits on failure."""
    typer.echo(f"  {label}...", nl=False)
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    ok = result.returncode == 0
    status = (
        typer.style(" ok", fg=typer.colors.GREEN)
        if ok
        else typer.style(" FAILED", fg=typer.colors.RED, bold=True)
    )
    typer.echo(status)
    if not ok:
        typer.echo((result.stdout + result.stderr).strip(), err=True)
        raise typer.Exit(1)


def _update_editable() -> None:
    """Dev path: uv sync, then migrate in-process (code is already current here)."""
    from wizard.cli.main import _reg_service

    repo_root = Path(__file__).resolve().parents[3]
    sync_args = (
        ["uv", "sync"]
        if shutil.which("uv")
        else [sys.executable, "-m", "pip", "install", "-e", str(repo_root)]
    )
    _run_update_step("sync deps", sync_args, repo_root)
    _reg_service.ensure_editable_pth()
    typer.echo("  run migrations... ", nl=False)
    try:
        run_migrations()
        typer.echo("ok")
    except Exception as exc:
        typer.echo(f"FAILED\n{exc}", err=True)
        raise typer.Exit(1) from exc


def _update_installed() -> None:
    """Installed path: uv tool upgrade, then migrate via the freshly-upgraded tool.

    This process still holds the pre-upgrade code, so its bundled migrations are
    stale — running `wizard migrate` in a subprocess picks up the new revisions.
    """
    if not shutil.which("uv"):
        typer.echo("uv not found — cannot upgrade", err=True)
        raise typer.Exit(1)
    _run_update_step("upgrade", ["uv", "tool", "upgrade", "wizard"], Path.home())
    _run_update_step("run migrations", ["wizard", "migrate"], Path.home())


def migrate() -> None:
    """Upgrade the Wizard database to the latest schema (alembic upgrade head)."""
    run_migrations()


def update(
    dev: bool = typer.Option(False, "--dev", help="Force editable update path (uv sync only)."),
) -> None:
    """Pull latest code (dev) or upgrade tool install, run migrations, re-register agents."""
    from wizard.cli.main import _display_agent_registration, _reg_service

    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()

    if registered:
        typer.echo("  unlinking old skills/hooks... ", nl=False)
        # deregister_agents removes skills and hooks based on the CURRENT (old) mirrored assets.
        _reg_service.deregister_agents(registered)
        typer.echo("ok")

    if dev or is_editable_install():
        _update_editable()
    else:
        _update_installed()

    agent_registration.refresh_hooks()
    _reg_service.refresh_skills()

    if registered:
        typer.echo("  re-linking skills/hooks... ", nl=False)
        results = _reg_service.register_agents(registered)
        typer.echo("ok")
        _display_agent_registration(results)
    else:
        typer.echo("\nNo registered agents found — run: wizard setup --agent <agent>")

    rprint(Panel(
        f"Skills cache: [dim]{_reg_service.WIZARD_HOME / 'skills'}[/dim]\n"
        "  ✅  Update complete — obsolete skills and hooks removed.",
        title="[green]Wizard updated[/green]", border_style="green",
    ))
