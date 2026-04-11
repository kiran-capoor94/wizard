import json
import logging
import shutil
from pathlib import Path

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="wizard",
    help="Wizard — local memory layer for AI agents",
    invoke_without_command=True,
)


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


@app.command()
def setup() -> None:
    """Create ~/.wizard, default config, and install skills."""
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
    from wizard.config import settings

    ok = True

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
