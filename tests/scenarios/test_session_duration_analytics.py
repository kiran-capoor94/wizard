"""Scenario: session duration is computed from WizardSession fields, never ToolCall timestamps.

Root cause of negative durations: ToolLoggingMiddleware logs the ToolCall
BEFORE running the tool. When session_start fires, current_session_id still
holds the previous session's ID, so the session_start ToolCall is attributed
to the wrong session.

Fix:
  User-closed: session.updated_at − session.created_at
  Abandoned:   session.last_active_at − session.created_at
  Open:        excluded from average
"""

import datetime

from sqlmodel import Session

from wizard.cli.analytics import query_sessions
from wizard.models import WizardSession


def test_session_duration_never_negative(db_session: Session):
    now = datetime.datetime.now().replace(microsecond=0)
    start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    # User-closed: 30-minute session (updated_at set explicitly to simulate session_end)
    s1 = WizardSession(summary="Done", closed_by="user", created_at=now)
    db_session.add(s1)
    db_session.flush()
    db_session.refresh(s1)
    s1.updated_at = now + datetime.timedelta(minutes=30)
    db_session.add(s1)
    db_session.flush()

    # Abandoned: 20-minute session
    s2 = WizardSession(
        summary="Auto-closed",
        closed_by="auto",
        created_at=now,
        last_active_at=now + datetime.timedelta(minutes=20),
    )
    db_session.add(s2)
    db_session.flush()

    # Open: no contribution to average
    db_session.add(WizardSession(created_at=now))
    db_session.flush()

    result = query_sessions(db_session, start, end)

    assert result["session_count"] == 3
    assert result["abandoned_count"] == 1
    assert result["abandoned_rate"] == round(1 / 3, 2)
    assert result["avg_duration_minutes"] == 25.0  # (30 + 20) / 2
    assert result["avg_duration_minutes"] >= 0


def test_open_sessions_excluded_from_duration_average(db_session: Session):
    now = datetime.datetime.now()
    start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    db_session.add(WizardSession(created_at=now))
    db_session.add(WizardSession(created_at=now))
    db_session.flush()

    result = query_sessions(db_session, start, end)

    assert result["session_count"] == 2
    assert result["avg_duration_minutes"] == 0.0


def test_abandoned_without_last_active_excluded_from_average(db_session: Session):
    now = datetime.datetime.now()
    start = datetime.date.today() - datetime.timedelta(days=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    db_session.add(WizardSession(
        summary="Auto-closed", closed_by="auto", created_at=now, last_active_at=None,
    ))
    db_session.flush()

    result = query_sessions(db_session, start, end)

    assert result["avg_duration_minutes"] == 0.0
