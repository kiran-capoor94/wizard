"""Scenario: AnalyticsRepository.get_tool_call_frequency counts by tool within window."""

import datetime

from wizard.models import ToolCall
from wizard.repositories.analytics import AnalyticsRepository


class TestGetToolCallFrequency:
    def test_counts_calls_by_tool(self, db_session):
        repo = AnalyticsRepository()
        db_session.add(ToolCall(tool_name="task_start", called_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)))
        db_session.add(ToolCall(tool_name="task_start", called_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)))
        db_session.add(ToolCall(tool_name="save_note", called_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)))
        db_session.flush()

        result = repo.get_tool_call_frequency(db_session, days=30)
        assert result["task_start"] == 2
        assert result["save_note"] == 1

    def test_excludes_calls_outside_window(self, db_session):
        repo = AnalyticsRepository()
        db_session.add(ToolCall(tool_name="old_tool", called_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)))
        db_session.flush()

        result = repo.get_tool_call_frequency(db_session, days=30)
        assert "old_tool" not in result
