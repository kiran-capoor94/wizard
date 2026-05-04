"""Smoke tests for dashboard Search and Timeline tab render functions."""
import sys
from unittest.mock import MagicMock, patch

_DUMMY_DATA = {
    "open_task_count": 0, "sessions_today": 0, "note_stats_7d": {
        "total": 0, "by_type": {}, "mental_model_coverage": 0, "unclassified": 0, "superseded": 0
    }, "session_stats_7d": {
        "session_count": 0, "avg_duration_minutes": 0, "abandoned_count": 0, "synthesis_failures": 0
    }, "task_stats_7d": {"worked": 0, "stale_count": 0},
    "compounding": 0, "tool_freq": {}, "recent_sessions": [],
    "open_tasks": [], "blocked_tasks": [], "note_velocity": {}, "session_velocity": {},
    "tool_calls_total": 0,
}

_st_mock = MagicMock()
_st_mock.tabs.return_value = [MagicMock() for _ in range(6)]
_st_mock.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]


def _load_dashboard():
    for mod in list(sys.modules):
        if "wizard.cli.dashboard" in mod:
            del sys.modules[mod]
    with patch.dict("sys.modules", {"streamlit": _st_mock, "pandas": MagicMock()}):
        with patch("wizard.repositories.analytics.AnalyticsRepository.get_compounding_score", return_value=0.5), \
             patch("wizard.repositories.analytics.AnalyticsRepository.get_note_stats", return_value=_DUMMY_DATA["note_stats_7d"]), \
             patch("wizard.repositories.analytics.AnalyticsRepository.get_session_stats", return_value=_DUMMY_DATA["session_stats_7d"]), \
             patch("wizard.repositories.analytics.AnalyticsRepository.get_task_stats", return_value=_DUMMY_DATA["task_stats_7d"]), \
             patch("wizard.repositories.analytics.AnalyticsRepository.get_tool_call_frequency", return_value={}), \
             patch("wizard.repositories.analytics.AnalyticsRepository.get_note_velocity", return_value={}), \
             patch("wizard.repositories.analytics.AnalyticsRepository.get_session_velocity", return_value={}), \
             patch("wizard.repositories.session.SessionRepository.count_today", return_value=0), \
             patch("wizard.repositories.session.SessionRepository.list_paginated", return_value=[]), \
             patch("wizard.repositories.task.TaskRepository.count_open_tasks", return_value=0), \
             patch("wizard.repositories.task.TaskRepository.get_open_task_contexts", return_value=[]), \
             patch("wizard.repositories.task.TaskRepository.get_blocked_task_contexts", return_value=[]):
            import wizard.cli.dashboard as dash
    return dash


def test_render_search_tab_importable():
    dash = _load_dashboard()
    assert callable(dash._render_search_tab)


def test_render_timeline_tab_importable():
    dash = _load_dashboard()
    assert callable(dash._render_timeline_tab)
