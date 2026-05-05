"""Health page — session breakdown, tool frequency, note quality."""

import datetime

import pandas as pd
import streamlit as st

from wizard.database import get_session
from wizard.repositories.analytics import AnalyticsRepository
from wizard.repositories.session import SessionRepository

_analytics = AnalyticsRepository()
_sessions = SessionRepository()

_SESSIONS_LIMIT = 30
_TOOL_WINDOW_DAYS = 30
_NOTE_WINDOW_DAYS = 7


def render() -> None:
    st.title("Health")
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=_NOTE_WINDOW_DAYS)

    with get_session() as db:
        recent_sessions = _sessions.list_paginated(db, limit=_SESSIONS_LIMIT)
        tool_freq = _analytics.get_tool_call_frequency(db, days=_TOOL_WINDOW_DAYS)
        note_stats = _analytics.get_note_stats(db, week_ago, today)
        durations = _analytics.get_session_durations(db, limit=_SESSIONS_LIMIT)

        st.subheader("Session Close Method Breakdown")
        close_methods: dict[str, int] = {}
        for s in recent_sessions:
            key = s.closed_by or "open"
            close_methods[key] = close_methods.get(key, 0) + 1
        if close_methods:
            st.bar_chart(
                pd.DataFrame(close_methods.items(), columns=["Method", "Count"]).set_index("Method")
            )

        st.subheader("Session Duration Distribution (last 30 closed, minutes)")
        if durations:
            st.bar_chart(pd.DataFrame({"Duration (min)": durations}))
        else:
            st.info("No closed sessions recorded.")

        st.subheader(f"Tool Call Frequency (last {_TOOL_WINDOW_DAYS} days)")
        if tool_freq:
            tf_df = (
                pd.DataFrame(tool_freq.items(), columns=["Tool", "Calls"])
                .sort_values("Calls", ascending=False)
                .head(15)
                .set_index("Tool")
            )
            st.bar_chart(tf_df)
        else:
            st.info("No tool calls recorded.")

        st.subheader("Note Quality (7d)")
        col1, col2, col3 = st.columns(3)
        col1.metric("Mental Model Coverage", f"{round(note_stats['mental_model_coverage'] * 100)}%")
        col2.metric("Unclassified Notes", note_stats["unclassified"])
        col3.metric("Superseded Notes", note_stats["superseded"])
