import logging

from sqlmodel import Session, col, func, select

from ..models import Note, WizardSession

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
