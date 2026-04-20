"""Scenario: analytics correctly reports abandoned session metrics."""

import datetime

import pytest
from sqlmodel import Session

from wizard.cli.analytics import query_sessions
from wizard.models import WizardSession


@pytest.fixture
def seed_sessions(db_session: Session):
    """Create sessions using WizardSession fields for duration control."""
    now = datetime.datetime.now().replace(microsecond=0)

    # Session 1: user-closed, 30-minute duration
    s1 = WizardSession(summary="Done", closed_by="user", created_at=now)
    db_session.add(s1)
    db_session.flush()
    db_session.refresh(s1)
    s1.updated_at = now + datetime.timedelta(minutes=30)
    db_session.add(s1)
    db_session.flush()

    # Session 2: auto-closed (abandoned), 20-minute duration
    s2 = WizardSession(
        summary="Auto-closed: 2 notes",
        closed_by="auto",
        created_at=now,
        last_active_at=now + datetime.timedelta(minutes=20),
    )
    db_session.add(s2)
    db_session.flush()

    # Session 3: still open (no duration contribution)
    s3 = WizardSession(created_at=now)
    db_session.add(s3)
    db_session.flush()

    return s1, s2, s3


def test_abandoned_analytics(db_session, seed_sessions):
    today = datetime.date.today()
    start = today - datetime.timedelta(days=1)
    end = today + datetime.timedelta(days=1)

    result = query_sessions(db_session, start, end)

    assert result["session_count"] == 3
    assert result["abandoned_count"] == 1
    assert result["abandoned_rate"] == round(1 / 3, 2)
    # avg_duration: s1=30min + s2=20min → avg=25.0; s3 excluded (open)
    assert result["avg_duration_minutes"] == 25.0
