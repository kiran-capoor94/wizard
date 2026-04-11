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
    "notion": {"token": "", "daily_page_id": "", "tasks_db_id": "", "meetings_db_id": ""},
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
