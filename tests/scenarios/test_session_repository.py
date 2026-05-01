import datetime

from wizard.models import WizardSession
from wizard.repositories.session import SessionRepository


def test_get_prior_summaries_exposes_raw_state(db_session):
    s1 = WizardSession(
        summary="did stuff",
        session_state='{"working_set": [1, 2], "intent": "test", "open_loops": [], "next_actions": []}',
        closed_by="hook",
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
    )
    db_session.add(s1)
    db_session.flush()
    s2 = WizardSession(created_at=datetime.datetime.now(), updated_at=datetime.datetime.now())
    db_session.add(s2)
    db_session.flush()

    repo = SessionRepository()
    summaries = repo.get_prior_summaries(db_session, current_session_id=s2.id)
    assert len(summaries) == 1
    assert summaries[0].raw_session_state == s1.session_state


def test_get_prior_summaries_corrupt_json_surfaces_raw(db_session):
    s1 = WizardSession(
        summary="did stuff", session_state="NOT_VALID_JSON", closed_by="hook",
        created_at=datetime.datetime.now(), updated_at=datetime.datetime.now(),
    )
    db_session.add(s1)
    db_session.flush()
    s2 = WizardSession(created_at=datetime.datetime.now(), updated_at=datetime.datetime.now())
    db_session.add(s2)
    db_session.flush()

    repo = SessionRepository()
    summaries = repo.get_prior_summaries(db_session, current_session_id=s2.id)
    assert summaries[0].raw_session_state == "NOT_VALID_JSON"
    assert summaries[0].task_ids == []
