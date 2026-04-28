import datetime
import json
import logging
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import sentry_sdk
from sqlmodel import Session, or_, select

from . import agent_registration
from .config import WIZARD_MODES
from .database import get_session
from .mid_session import cancel_mid_session_synthesis
from .models import Note, NoteType, WizardSession
from .repositories import NoteRepository
from .schemas import ClosedSessionSummary, SessionState
from .security import SecurityService

if TYPE_CHECKING:
    from wizard.config import Settings

logger = logging.getLogger(__name__)


class RegistrationService:
    """Handles agent registration, setup, and uninstallation logic."""

    def __init__(self, settings: "Settings"):
        self._settings = settings
        self.WIZARD_HOME = Path(settings.db).parent

    def ensure_wizard_home(self) -> None:
        self.WIZARD_HOME.mkdir(parents=True, exist_ok=True)

    def initialize_config(self) -> str:
        config_path = self.WIZARD_HOME / "config.json"
        if not config_path.exists():
            config_data = self._settings.model_dump(exclude={"name", "version", "db", "sentry"})
            config_data["modes"]["allowed"] = sorted(WIZARD_MODES)
            config_path.write_text(json.dumps(config_data, indent=2))
            return f"Created default config at {config_path}"
        return f"Config already exists at {config_path}"

    def initialize_allowlist(self) -> str:
        allowlist_path = self.WIZARD_HOME / "allowlist.txt"
        if not allowlist_path.exists():
            allowlist_path.touch()
            return f"Created allowlist file at {allowlist_path}"
        return f"Allowlist already exists at {allowlist_path}"

    def refresh_skills(self, source_override: Path | None = None) -> str:
        dest = self.WIZARD_HOME / "skills"
        source = source_override or Path(__file__).resolve().parent / "skills"
        if source.exists():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            self._merge_wizard_modes()
            return f"Installed skills to {dest}"
        return "No skills found in package — skipping skill install"

    def _merge_wizard_modes(self) -> None:
        config_path = self.WIZARD_HOME / "config.json"
        if not config_path.exists():
            return
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            return
        modes = config.setdefault("modes", {})
        existing = set(modes.get("allowed", []))
        modes["allowed"] = sorted(existing | set(WIZARD_MODES))
        config_path.write_text(json.dumps(config, indent=2))

    def register_agents(self, agent_ids: list[str]) -> list[dict]:
        results = []
        source = Path(__file__).resolve().parent / "skills"
        for aid in agent_ids:
            res = {"id": aid, "success": False, "parts": [], "error": None}
            try:
                agent_registration.register(aid)
                res["parts"].append("MCP")
                if agent_registration.register_hook(aid):
                    res["parts"].append("hook")
                if source.exists() and agent_registration.install_skills(aid, source):
                    res["parts"].append("skills")
                res["success"] = True
            except Exception as e:
                res["error"] = str(e)
            results.append(res)
        return results

    def deregister_agents(self, agent_ids: list[str]) -> list[dict]:
        results = []
        source = Path(__file__).resolve().parent / "skills"
        for aid in agent_ids:
            res = {"id": aid, "success": False, "parts": [], "error": None}
            try:
                agent_registration.deregister(aid)
                res["parts"].append("MCP")
                if agent_registration.deregister_hook(aid):
                    res["parts"].append("hook")
                if source.exists() and agent_registration.uninstall_skills(aid, source):
                    res["parts"].append("skills")
                res["success"] = True
            except Exception as e:
                res["error"] = str(e)
            results.append(res)
        return results

    def uninstall_wizard(self) -> str:
        if self.WIZARD_HOME.exists():
            shutil.rmtree(self.WIZARD_HOME)
            return f"Removed {self.WIZARD_HOME}"
        return "Nothing to remove"

    @staticmethod
    def ensure_editable_pth() -> None:
        """Clear the UF_HIDDEN macOS flag from the hatchling editable .pth file."""
        repo_root = Path(__file__).resolve().parents[2]
        py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = repo_root / ".venv" / "lib" / py_ver / "site-packages"
        if not site_packages.exists():
            return

        pth_file = site_packages / "_editable_impl_wizard.pth"
        if not pth_file.exists():
            return

        if not hasattr(os, "chflags"):
            return

        st = os.lstat(pth_file)
        if getattr(st, "st_flags", 0) & stat.UF_HIDDEN:
            os.chflags(pth_file, st.st_flags & ~stat.UF_HIDDEN)


class SessionCloser:
    """Auto-closes abandoned sessions using synthetic summaries.

    Inline (close_recent_abandoned): runs inside session_start, safe for the stdio transport.
    Background (close_abandoned_background): asyncio task dispatched after session_start returns.
    """

    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        security: SecurityService | None = None,
        settings: "Settings" | None = None,
    ):
        self._note_repo = note_repo or NoteRepository()
        self._security = security or SecurityService()
        self._settings = settings

    async def close_recent_abandoned(
        self,
        db: Session,
        current_session_id: int,
    ) -> list[ClosedSessionSummary]:
        """Close sessions abandoned within the last 2h inline using synthetic summaries.

        Does not call ctx.sample() — sampling during an active tool call deadlocks
        the stdio transport (server sends createMessage while client waits for
        session_start response).
        """
        recent = self._find_recent_abandoned(db, current_session_id)
        return [await self._close_one(db, s) for s in recent]

    async def close_abandoned_background(self, current_session_id: int) -> None:
        """Synthetically close sessions older than 24h with no summary. Opens its own DB session."""
        try:
            with get_session() as db:
                old = self._find_old_abandoned(db, current_session_id)
                count = 0
                for session in old:
                    try:
                        await self._close_one(db, session)
                        count += 1
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        logger.warning(
                            "close_abandoned_background: failed for session %d: %s",
                            session.id,
                            e,
                        )
                logger.info("close_abandoned_background: closed %d session(s)", count)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            logger.warning("close_abandoned_background: outer failure: %s", e)

    def _find_recent_abandoned(
        self,
        db: Session,
        current_session_id: int,
        max_age_hours: int = 2,
        limit: int = 3,
    ) -> list[WizardSession]:
        """Sessions with no summary abandoned within the last max_age_hours."""
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=max_age_hours)
        stmt = (
            select(WizardSession)
            .where(
                WizardSession.summary == None,  # noqa: E711
                or_(
                    WizardSession.closed_by == None,  # noqa: E711
                    WizardSession.closed_by == "hook",
                ),
                WizardSession.id != current_session_id,
                WizardSession.created_at >= cutoff,
            )
            .order_by(WizardSession.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        return list(db.exec(stmt).all())

    def _find_old_abandoned(
        self,
        db: Session,
        current_session_id: int,
        min_age_hours: int = 2,
    ) -> list[WizardSession]:
        """Sessions with no summary older than min_age_hours."""
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=min_age_hours)
        stmt = (
            select(WizardSession)
            .where(
                WizardSession.summary == None,  # noqa: E711
                or_(
                    WizardSession.closed_by == None,  # noqa: E711
                    WizardSession.closed_by == "hook",
                ),
                WizardSession.id != current_session_id,
                WizardSession.created_at < cutoff,
            )
            .order_by(WizardSession.created_at.desc())  # type: ignore[union-attr]
        )
        return list(db.exec(stmt).all())

    async def _close_one(
        self,
        db: Session,
        session: WizardSession,
    ) -> ClosedSessionSummary:
        session_id = session.id
        assert session_id is not None

        if session.agent_session_id:
            cancel_mid_session_synthesis(session.agent_session_id)

        notes = self._get_session_notes(db, session_id)
        task_ids = list({n.task_id for n in notes if n.task_id is not None})
        note_count = len(notes)
        state = SessionState(
            intent="",
            working_set=task_ids,
            state_delta="",
            open_loops=[],
            next_actions=[],
            closure_status="interrupted",
        )
        summary_text, closed_via = self._synthetic_summary(session, notes, task_ids)
        clean_summary = self._security.scrub(summary_text).clean
        session.summary = clean_summary
        session.session_state = state.model_dump_json()
        if session.closed_by is None:
            session.closed_by = "auto"
        db.add(session)
        db.flush()
        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary,
            session_id=session_id,
            artifact_id=session.artifact_id,
            artifact_type="session",
        )
        self._note_repo.save(db, note)
        return ClosedSessionSummary(
            session_id=session_id,
            summary=clean_summary,
            closed_via=closed_via,
            task_ids=task_ids,
            note_count=note_count,
        )

    def _get_session_notes(self, db: Session, session_id: int) -> list[Note]:
        stmt = (
            select(Note)
            .where(Note.session_id == session_id)
            .order_by(Note.created_at.asc())  # type: ignore[union-attr]
        )
        return list(db.exec(stmt).all())

    def _synthetic_summary(
        self,
        session: WizardSession,
        notes: list[Note],
        task_ids: list[int],
    ) -> tuple[str, str]:
        note_count = len(notes)
        task_count = len(task_ids)
        last_activity = session.last_active_at or session.updated_at
        return (
            f"Auto-closed: {note_count} note(s) across {task_count} task(s). "
            f"Last activity: {last_activity}."
        ), "synthetic"
