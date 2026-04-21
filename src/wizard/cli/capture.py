"""CLI command for synthesising agent transcripts into notes.

Extracted from main.py to keep it under the 500-line cap.
"""

import datetime
from pathlib import Path

import typer
from sqlmodel import select

from wizard.config import settings
from wizard.database import get_session as get_db_session
from wizard.models import WizardSession
from wizard.repositories import NoteRepository, TaskRepository
from wizard.security import SecurityService
from wizard.synthesis import OllamaSynthesiser
from wizard.transcript import TranscriptReader


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
    if not main_path.exists():
        return []
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
            pass  # file deleted between glob and stat
    return [main_path] + siblings


def capture(
    close: bool = typer.Option(False, "--close", help="Mark session as closed by hook"),
    transcript: str = typer.Option("", "--transcript", help="Path to transcript file"),
    agent: str = typer.Option("", "--agent", help="Agent name"),
    session_id: int | None = typer.Option(
        None, "--session-id", help="Wizard session ID"
    ),
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

        security = SecurityService(
            allowlist=settings.scrubbing.allowlist, enabled=settings.scrubbing.enabled
        )
        synthesiser = OllamaSynthesiser(
            reader=TranscriptReader(),
            note_repo=NoteRepository(),
            security=security,
            t_repo=TaskRepository(),
        )
        total_notes, synthesised_via = 0, "fallback"
        for i, path in enumerate(transcripts):
            try:
                result = synthesiser.synthesise_path(db, session, path)
                total_notes += result.notes_created
                synthesised_via = result.synthesised_via
            except Exception as e:
                typer.echo(f"Synthesis failed for {path}: {e}", err=True)
                if i == 0:
                    raise typer.Exit(1) from None
        typer.echo(
            f"Session {session.id}: {total_notes} note(s) via {synthesised_via}."
        )
