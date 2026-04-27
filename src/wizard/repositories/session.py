import logging

from pydantic import ValidationError
from sqlmodel import Session, col, func, select

from ..models import Note, WizardSession
from ..schemas import PriorSessionSummary, SessionState

logger = logging.getLogger(__name__)


class SessionRepository:
    def list_paginated(
        self,
        db: Session,
        closure_status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WizardSession]:
        stmt = select(WizardSession)
        if closure_status_filter:
            stmt = stmt.where(WizardSession.closed_by == closure_status_filter)
        stmt = (
            stmt.order_by(col(WizardSession.created_at).desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.exec(stmt).all())

    def count(self, db: Session, closure_status_filter: str | None = None) -> int:
        stmt = select(func.count()).select_from(WizardSession)
        if closure_status_filter:
            stmt = stmt.where(WizardSession.closed_by == closure_status_filter)
        return db.exec(stmt).one()

    def get(self, db: Session, session_id: int) -> WizardSession | None:
        return db.exec(
            select(WizardSession).where(WizardSession.id == session_id)
        ).first()

    def get_prior_summaries(
        self, db: Session, current_session_id: int
    ) -> list[PriorSessionSummary]:
        """Return the 3 most recent closed sessions with summaries for prior-context surfacing."""
        prior_sessions = db.exec(
            select(WizardSession)
            .where(
                WizardSession.summary != None,  # noqa: E711
                WizardSession.id != current_session_id,
            )
            .order_by(col(WizardSession.created_at).desc())
            .limit(3)
        ).all()

        result = []
        for s in prior_sessions:
            if s.id is None or s.summary is None:
                continue
            task_ids: list[int] = []
            if s.session_state:
                try:
                    state_obj = SessionState.model_validate_json(s.session_state)
                    task_ids = state_obj.working_set
                except (ValueError, ValidationError) as e:
                    logger.warning("prior_summaries: bad session_state sid=%s: %s", s.id, e)
            result.append(
                PriorSessionSummary(
                    session_id=s.id,
                    summary=s.summary,
                    closed_at=s.updated_at,
                    task_ids=task_ids,
                )
            )
        return result

    def get_most_recent_id(self, db: Session) -> int | None:
        """Return the most recently created WizardSession id, or None if none exists."""
        return db.exec(
            select(WizardSession.id)
            .order_by(col(WizardSession.created_at).desc(), col(WizardSession.id).desc())
            .limit(1)
        ).first()

    def set_active_mode(self, db: Session, session_id: int, mode: str | None) -> WizardSession:
        """Set active_mode on a session, flush, and return the updated row.

        Raises ValueError if the session does not exist.
        """
        session = self.get(db, session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        session.active_mode = mode
        db.add(session)
        db.flush()
        return session



def find_latest_session_with_notes(db: Session) -> WizardSession | None:
    """Most recent WizardSession that has at least one associated Note."""
    subq = select(Note).where(Note.session_id == WizardSession.id).exists()
    stmt = (
        select(WizardSession)
        .where(subq)
        .order_by(col(WizardSession.created_at).desc())
        .limit(1)
    )
    results = db.exec(stmt).all()
    return results[0] if results else None
