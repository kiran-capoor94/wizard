"""Scenario: analytics correctly reports abandoned session metrics."""

import datetime

import pytest
from sqlmodel import Session

from wizard.cli.analytics import query_sessions
from wizard.models import ToolCall, WizardSession


@pytest.fixture
def seed_sessions(db_session: Session):
    """Create sessions with different closed_by values and ToolCall records."""
    now = datetime.datetime.now()

    # Session 1: user-closed (has session_end ToolCall)
    s1 = WizardSession(summary="Done", closed_by="user")
    db_session.add(s1)
    db_session.flush()
    db_session.refresh(s1)
    db_session.add(ToolCall(session_id=s1.id, tool_name="session_start", called_at=now))
    db_session.add(ToolCall(
        session_id=s1.id, tool_name="session_end",
        called_at=now + datetime.timedelta(minutes=30),
    ))

    # Session 2: auto-closed (abandoned, has last_active_at)
    s2 = WizardSession(
        summary="Auto-closed: 2 notes",
        closed_by="auto",
        last_active_at=now + datetime.timedelta(minutes=20),
    )
    db_session.add(s2)
    db_session.flush()
    db_session.refresh(s2)
    db_session.add(ToolCall(session_id=s2.id, tool_name="session_start", called_at=now))

    # Session 3: still open (no summary, no closed_by)
    s3 = WizardSession()
    db_session.add(s3)
    db_session.flush()
    db_session.refresh(s3)
    db_session.add(ToolCall(session_id=s3.id, tool_name="session_start", called_at=now))

    db_session.flush()
    return s1, s2, s3


def test_abandoned_analytics(db_session, seed_sessions):
    s1, s2, s3 = seed_sessions
    today = datetime.date.today()
    start = today - datetime.timedelta(days=1)
    end = today + datetime.timedelta(days=1)

    result = query_sessions(db_session, start, end)

    assert result["session_count"] == 3
    assert result["abandoned_count"] == 1  # only s2 (closed_by="auto")
    assert result["abandoned_rate"] == round(1 / 3, 2)

    # avg_duration should include both user-closed (30min) and auto-closed (20min)
    # s3 has no duration data, so 2 sessions with durations: avg = 25.0
    assert result["avg_duration_minutes"] == 25.0
