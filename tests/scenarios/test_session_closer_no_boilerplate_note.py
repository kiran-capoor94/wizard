"""Scenario: SessionCloser must not persist the synthetic auto-close summary as a Note.

The synthetic summary ("Auto-closed: N note(s)...") is boilerplate produced when
an interrupted session has no real user-authored summary. session.summary should
still record it (for resume_session context), but it must not also show up as a
SESSION_SUMMARY Note — that would pollute search/memory with content nobody wrote.
"""

from sqlalchemy import select
from sqlmodel import Session

from wizard.database import engine
from wizard.models import Note, WizardSession
from wizard.services import SessionCloser


async def test_session_closer_skips_boilerplate_note_for_synthetic_summary(security):
    closer = SessionCloser(security=security)

    with Session(engine) as db:
        abandoned = WizardSession(agent="claude-code")
        current = WizardSession(agent="claude-code")
        db.add(abandoned)
        db.add(current)
        db.flush()
        session_id = abandoned.id
        current_session_id = current.id
        db.commit()

        try:
            closed = await closer.close_recent_abandoned(db, current_session_id)
            db.commit()

            assert len(closed) == 1
            assert closed[0].session_id == session_id
            assert closed[0].closed_via == "synthetic"

            db.refresh(abandoned)
            assert abandoned.summary is not None
            assert abandoned.summary.startswith("Auto-closed:")

            notes = db.execute(
                select(Note).where(Note.session_id == session_id)
            ).scalars().all()
            assert all(not n.content.startswith("Auto-closed:") for n in notes)
        finally:
            notes = db.execute(
                select(Note).where(Note.session_id.in_([session_id, current_session_id]))
            ).scalars().all()
            for n in notes:
                db.delete(n)
            db.flush()
            db.delete(abandoned)
            db.delete(current)
            db.commit()
