"""CLI command for synthesising agent transcripts into notes.

Extracted from main.py to keep it under the 500-line cap.
"""

import datetime
import logging
from pathlib import Path

import typer
from sqlmodel import select

from wizard.config import settings
from wizard.database import get_session as get_db_session
from wizard.models import WizardSession
from wizard.repositories import NoteRepository, TaskRepository
from wizard.schemas import SynthesisNote
from wizard.security import SecurityService
from wizard.synthesis import Synthesiser
from wizard.transcript import TranscriptReader

logger = logging.getLogger(__name__)


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
    """Return all transcript paths to synthesise for this session.

    OpenCode stores data in a directory tree keyed by session ID; there is no
    single transcript file. We synthesise by passing a synthetic path whose
    stem is the session ID — TranscriptReader._read_opencode uses only path.stem.
    """
    if session.agent == "opencode":
        if not session.agent_session_id:
            return []
        return [
            Path.home()
            / ".local"
            / "share"
            / "opencode"
            / "storage"
            / "message"
            / session.agent_session_id
            / f"{session.agent_session_id}.json"
        ]
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


def capture(  # noqa: C901
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
    """Capture agent session data and synthesise transcript into notes."""
    if not close:
        typer.echo("Only --close mode is supported.")
        raise typer.Exit(0)

    security = SecurityService(
        allowlist=settings.scrubbing.allowlist, enabled=settings.scrubbing.enabled
    )
    synthesiser = Synthesiser(
        reader=TranscriptReader(),
        note_repo=NoteRepository(),
        security=security,
        t_repo=TaskRepository(),
    )

    # 1. Fetch metadata and open tasks in a brief transaction.
    logger.info("capture: opening transaction 1 (metadata fetch)")
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

        # Prepare data for synthesis outside the session
        agent_name = session.agent
        session_db_id = session.id
        task_table, valid_task_ids = synthesiser.prepare_task_table(db)
    logger.info("capture: transaction 1 closed")

    # 2. Perform slow LLM synthesis (DB is unlocked).
    logger.info("capture: starting LLM phase (DB unlocked)")
    total_notes_data: list[SynthesisNote] = []
    for path in transcripts:
        try:
            notes = synthesiser.generate_notes(path, agent_name, task_table)
            if notes:
                total_notes_data.extend(notes)
        except Exception as e:
            typer.echo(f"Synthesis failed for {path}: {e}", err=True)
            raise typer.Exit(1) from None
    logger.info("capture: LLM phase complete")

    # 3. Persist all results in a final transaction.
    if not total_notes_data:
        typer.echo(f"Session {session_db_id}: no notes generated, marking as synthesised.")
        with get_db_session() as db:
            session = db.get(WizardSession, session_db_id)
            if session:
                session.is_synthesised = True
                db.add(session)
        return

    logger.info("capture: opening transaction 2 (persistence)")
    with get_db_session() as db:
        session = db.get(WizardSession, session_db_id)
        if not session:
            typer.echo(f"Error: Session {session_db_id} disappeared during synthesis.", err=True)
            raise typer.Exit(1)

        result = synthesiser.persist(
            db, total_notes_data, session, valid_task_ids, terminal=True
        )
        typer.echo(
            f"Session {session.id}: {result.notes_created} note(s) via {result.synthesised_via}."
        )
