import datetime
import logging

from fastmcp import Context
from sqlmodel import Session, or_, select

from .database import get_session
from .models import Note, NoteType, WizardSession
from .repositories import NoteRepository
from .schemas import AutoCloseSummary, ClosedSessionSummary, SessionState
from .security import SecurityService

logger = logging.getLogger(__name__)


class SessionCloser:
    """Auto-closes abandoned sessions with a three-tier fallback chain:
    1. LLM sampling via ctx.sample()
    2. Synthetic summary from DB data
    3. Minimal warn fallback
    """

    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        security: SecurityService | None = None,
    ):
        self._note_repo = note_repo or NoteRepository()
        self._security = security or SecurityService()

    async def close_recent_abandoned(
        self,
        db: Session,
        ctx: Context,
        current_session_id: int,
    ) -> list[ClosedSessionSummary]:
        """Close sessions abandoned within the last 2h inline. Uses LLM synthesis via ctx."""
        recent = self._find_recent_abandoned(db, current_session_id)
        return [await self.close_one(db, s, ctx) for s in recent]

    async def close_abandoned_background(self, current_session_id: int) -> None:
        """Synthetically close sessions older than 24h with no summary. Opens its own DB session.

        Hook-marked sessions (with transcripts) are handled inline in session_start so that
        ctx.sample() is available. This task only handles sessions with closed_by=None."""
        try:
            with get_session() as db:
                old = self._find_old_abandoned(db, current_session_id)
                count = 0
                for session in old:
                    try:
                        await self.close_one(db, session, ctx=None)
                        count += 1
                    except Exception as e:
                        logger.warning(
                            "close_abandoned_background: failed for session %d: %s",
                            session.id, e,
                        )
                logger.info("close_abandoned_background: closed %d session(s)", count)
        except Exception as e:
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
        return list(db.execute(stmt).scalars().all())

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
        return list(db.execute(stmt).scalars().all())

    async def close_one(
        self,
        db: Session,
        session: WizardSession,
        ctx: Context | None = None,
    ) -> ClosedSessionSummary:
        session_id = session.id
        assert session_id is not None
        notes = self._get_session_notes(db, session_id)
        task_ids = list({n.task_id for n in notes if n.task_id is not None})
        note_count = len(notes)
        state = SessionState(
            intent="", working_set=task_ids, state_delta="",
            open_loops=[], next_actions=[], closure_status="interrupted",
        )
        summary_text: str | None = None
        closed_via = ""
        if ctx is not None:
            summary_text, closed_via = await self._try_sampling(ctx, notes)
        if summary_text is None:
            summary_text, closed_via = self._synthetic_summary(session, notes, task_ids)
        clean_summary = self._security.scrub(summary_text).clean
        session.summary = clean_summary
        session.session_state = state.model_dump_json()
        if session.closed_by is None:
            session.closed_by = "auto"
        db.add(session)
        db.flush()
        note = Note(
            note_type=NoteType.SESSION_SUMMARY, content=clean_summary,
            session_id=session_id,
        )
        self._note_repo.save(db, note)
        return ClosedSessionSummary(
            session_id=session_id, summary=clean_summary,
            closed_via=closed_via, task_ids=task_ids, note_count=note_count,
        )

    def _get_session_notes(self, db: Session, session_id: int) -> list[Note]:
        stmt = (
            select(Note)
            .where(Note.session_id == session_id)
            .order_by(Note.created_at.asc())  # type: ignore[union-attr]
        )
        return list(db.exec(stmt).all())

    async def _try_sampling(
        self, ctx: Context, notes: list[Note]
    ) -> tuple[str | None, str]:
        if not notes:
            return None, ""
        prompt = self._build_sampling_prompt(notes)
        try:
            result = await ctx.sample(
                messages=prompt,
                system_prompt=(
                    "You are summarising an abandoned coding session. "
                    "Be concise. Focus on what was accomplished and what remains."
                ),
                result_type=AutoCloseSummary,
                max_tokens=500,
                temperature=0.3,
            )
            auto_summary: AutoCloseSummary = result.result
            return auto_summary.summary, "sampling"
        except Exception as e:
            logger.warning("SessionCloser sampling failed: %s", e)
            return None, ""

    def _build_sampling_prompt(self, notes: list[Note]) -> str:
        lines = ["The following notes were saved during an abandoned session:\n"]
        for n in notes:
            lines.append(f"- [{n.note_type.value}] {n.content[:300]}")
        lines.append(
            "\nSummarise what was accomplished, the likely intent, "
            "and any open loops."
        )
        return "\n".join(lines)

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
