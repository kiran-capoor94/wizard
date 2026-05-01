"""Scenario: SessionRepository.count_today returns sessions created today."""

import datetime

from wizard.models import WizardSession
from wizard.repositories.session import SessionRepository


class TestSessionCountToday:
    def test_counts_sessions_created_today(self, db_session):
        repo = SessionRepository()
        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)
        db_session.add(WizardSession(
            created_at=today, updated_at=today, closed_by="hook",
        ))
        db_session.add(WizardSession(
            created_at=yesterday, updated_at=yesterday, closed_by="hook",
        ))
        db_session.flush()

        result = repo.count_today(db_session)
        assert result == 1

    def test_returns_zero_when_no_sessions_today(self, db_session):
        repo = SessionRepository()
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        db_session.add(WizardSession(
            created_at=yesterday, updated_at=yesterday, closed_by="hook",
        ))
        db_session.flush()

        result = repo.count_today(db_session)
        assert result == 0
