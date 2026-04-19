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
from sqlmodel import select

from wizard import agent_registration
from wizard.cli import analytics as analytics_module
from wizard.cli.doctor import db_is_healthy, doctor
from wizard.config import settings
from wizard.database import get_session as get_db_session
from wizard.models import WizardSession
from wizard.repositories import NoteRepository
from wizard.security import SecurityService
from wizard.transcript import OllamaSynthesiser, TranscriptReader

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="wizard",
    invoke_without_command=True,
    help="Wizard — local memory layer for AI agents.",
)

app.command()(doctor)

configure_app = typer.Typer(help="Configure wizard settings.")
app.add_typer(configure_app, name="configure")

WIZARD_HOME = Path.home() / ".wizard"

_DEFAULT_CONFIG = {
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


def _register_agents(agent_ids: list[str], verb: str = "Registered") -> None:
    """Register + install hooks for each agent ID, echoing the result."""
    for aid in agent_ids:
        try:
            agent_registration.register(aid)
            hook_ok = agent_registration.register_hook(aid)
            typer.echo(f"  {verb} {aid}" + (" + hook" if hook_ok else ""))
        except Exception as exc:
            typer.echo(f"  Warning: could not register {aid}: {exc}", err=True)


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

    _register_agents(agents_to_register, verb="Registered")
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
    typer.echo(f"  Agent  {', '.join(agents_to_register)}")
    typer.echo("\nTo configure a knowledge store, run: wizard configure knowledge-store")


@configure_app.command("knowledge-store")
def configure_knowledge_store() -> None:
    """Configure where session summaries are written."""
    config_file = Path.home() / ".wizard" / "config.json"
    existing = json.loads(config_file.read_text()) if config_file.exists() else {}

    ks_type = typer.prompt(
        "Knowledge store type",
        default="",
        prompt_suffix=" [notion/obsidian/none]: ",
    ).strip().lower()
    if ks_type == "none":
        ks_type = ""

    if ks_type not in ("notion", "obsidian", ""):
        typer.echo(f"Unknown type: {ks_type}. Valid: notion, obsidian, or leave blank for none.")
        raise typer.Exit(1)

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
            agent_registration.deregister_hook(aid)
            typer.echo(f"  Removed wizard from {aid}")
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
    _register_agents(registered, verb="Re-registered")

    typer.echo("Wizard updated.")

def _find_capture_session(db, session_id: int | None) -> WizardSession | None:
    """Return the target session for capture: by ID or latest unsynthesised within 24h."""
    if session_id is not None:
        session = db.get(WizardSession, session_id)
        if session is not None and session.is_synthesised:
            return None
        return session
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
    return db.exec(
        select(WizardSession)
        .where(
            WizardSession.is_synthesised == False,  # noqa: E712
            WizardSession.created_at >= cutoff,
        )
        .order_by(WizardSession.created_at.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()

def _apply_hook_metadata(
    session: WizardSession,
    transcript: str,
    agent: str,
    agent_session_id: str | None,
) -> None:
    """Stamp hook-supplied metadata onto a session (in-place). Does not flush."""
    if transcript:
        session.transcript_path = transcript
    if agent:
        session.agent = agent
    if agent_session_id and not session.agent_session_id:
        session.agent_session_id = agent_session_id
    if session.closed_by is None:
        session.closed_by = "hook"

def _collect_transcripts(session: WizardSession) -> list[Path]:
    """Return all transcript paths to synthesise for this session."""
    if not session.transcript_path:
        return []
    main_path = Path(session.transcript_path)
    project_dir = main_path.parent
    session_start_ts = session.created_at.timestamp() if session.created_at else 0.0
    siblings = []
    for p in project_dir.glob("*.jsonl"):
        if p == main_path:
            continue
        try:
            if p.stat().st_mtime >= session_start_ts:
                siblings.append(p)
        except OSError:
            pass  # file deleted between glob and stat — skip
    return [main_path] + siblings

@app.command()
def capture(
    close: bool = typer.Option(False, "--close", help="Mark session as closed by hook"),
    transcript: str = typer.Option("", "--transcript", help="Path to transcript file"),
    agent: str = typer.Option("", "--agent", help="Agent name"),
    session_id: int | None = typer.Option(None, "--session-id", help="Wizard session ID"),
    agent_session_id: str | None = typer.Option(
        None, "--agent-session-id", help="Agent-assigned session UUID"
    ),
) -> None:
    """Capture agent session data and synthesise transcript into notes via Ollama."""
    if not close:
        typer.echo("Only --close mode is supported.")
        raise typer.Exit(0)

    with get_db_session() as db:
        session = _find_capture_session(db, session_id)
        if session is None:
            typer.echo("No unsynthesised session found within 24h.")
            raise typer.Exit(0)

        _apply_hook_metadata(session, transcript, agent, agent_session_id)
        db.add(session)
        db.flush()
        if not settings.synthesis.enabled:
            typer.echo(f"Session {session.id} marked (synthesis disabled).")
            return

        transcripts = _collect_transcripts(session)
        if not transcripts:
            typer.echo(f"Session {session.id}: no transcript path, skipping synthesis.")
            return

        synthesiser = OllamaSynthesiser(
            reader=TranscriptReader(),
            note_repo=NoteRepository(),
            security=SecurityService(
                allowlist=settings.scrubbing.allowlist,
                enabled=settings.scrubbing.enabled,
            ),
        )
        total_notes, synthesised_via = 0, "fallback"
        for path in transcripts:
            try:
                result = synthesiser.synthesise_path(db, session, path)
                total_notes += result.notes_created
                synthesised_via = result.synthesised_via
            except Exception as e:
                typer.echo(f"Synthesis failed for {path}: {e}", err=True)
        typer.echo(f"Session {session.id}: {total_notes} note(s) via {synthesised_via}.")
