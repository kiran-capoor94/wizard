"""Wizard health dashboard — Streamlit app.

Launch via: wizard dashboard
Or directly: streamlit run src/wizard/cli/dashboard.py
"""

import datetime
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from wizard.config import settings
from wizard.database import get_session
from wizard.repositories.analytics import AnalyticsRepository
from wizard.repositories.note import NoteRepository
from wizard.repositories.session import SessionRepository
from wizard.repositories.task import TaskRepository

_analytics_repo = AnalyticsRepository()
_note_repo = NoteRepository()
_session_repo = SessionRepository()
_task_repo = TaskRepository()

_NOTE_WINDOW_DAYS = 7
_TOOL_WINDOW_DAYS = 30
_RECENT_SESSIONS_LIMIT = 10
_NOTE_CONTENT_CAP = 1000
_TOP_TASKS_LIMIT = 5


def _load_dashboard_data() -> dict:
    if not Path(settings.db).exists() and settings.db != ":memory:":
        st.error("Database not found. Run 'wizard setup' first.")
        st.stop()
    with get_session() as db:
        latest_session_id = _session_repo.get_most_recent_id(db)
        latest_session = (
            _session_repo.get(db, latest_session_id) if latest_session_id else None
        )
        recent_sessions = _session_repo.list_paginated(db, limit=_RECENT_SESSIONS_LIMIT)
        recent_notes = _note_repo.get_recent(db, days=_NOTE_WINDOW_DAYS)
        by_type: dict[str, int] = {}
        for n in recent_notes:
            key = n.note_type.value if hasattr(n.note_type, "value") else str(n.note_type)
            by_type[key] = by_type.get(key, 0) + 1
        note_stats = {"by_type": by_type}
        tool_freq = _analytics_repo.get_tool_call_frequency(db, days=_TOOL_WINDOW_DAYS)
    return {
        "latest_session": latest_session,
        "recent_sessions": recent_sessions,
        "note_stats": note_stats,
        "recent_notes": recent_notes,
        "tool_freq": tool_freq,
    }


def _render_active_session(data: dict) -> None:
    st.subheader("Active Session")
    session = data["latest_session"]
    if session is None:
        st.info("No sessions found.")
        return
    col1, col2, col3 = st.columns(3)
    col1.metric("Session ID", session.id)
    col2.metric("Status", session.closed_by or "open")
    col3.metric("Synthesis", session.synthesis_status or "pending")
    st.caption(f"Started: {session.created_at.strftime('%Y-%m-%d %H:%M')}")


def _render_recent_notes(data: dict) -> None:
    st.subheader(f"Recent Notes (last {_NOTE_WINDOW_DAYS} days)")
    by_type: dict[str, int] = data["note_stats"].get("by_type", {})
    if not by_type:
        st.info("No notes in the last 7 days.")
        return
    chart_df = pd.DataFrame(
        {"type": list(by_type.keys()), "count": list(by_type.values())}
    ).set_index("type")
    st.bar_chart(chart_df)
    st.dataframe(chart_df.reset_index().rename(columns={"type": "Note Type", "count": "Count"}))


def _render_synthesis_health(data: dict) -> None:
    st.subheader("Synthesis Health (last 10 sessions)")
    sessions = data["recent_sessions"]
    if not sessions:
        st.info("No sessions found.")
        return
    rows = [
        {
            "ID": s.id,
            "Started": s.created_at.strftime("%Y-%m-%d %H:%M"),
            "Closed By": s.closed_by or "open",
            "Synthesis": s.synthesis_status or "pending",
        }
        for s in sessions
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def _render_memory_utilisation(data: dict) -> None:
    st.subheader("Memory Utilisation")
    recent_notes = data["recent_notes"]
    total = len(recent_notes)
    avg_length = round(sum(len(n.content or "") for n in recent_notes) / total, 1) if total else 0.0
    col1, col2, col3 = st.columns(3)
    col1.metric("Notes (7d)", total)
    col2.metric("Avg Length", f"{avg_length} chars")
    col3.metric("Cap", f"{_NOTE_CONTENT_CAP} chars")
    task_counts: dict[int, int] = {}
    for note in recent_notes:
        if note.task_id is not None:
            task_counts[note.task_id] = task_counts.get(note.task_id, 0) + 1
    top = sorted(task_counts.items(), key=lambda x: x[1], reverse=True)[:_TOP_TASKS_LIMIT]
    if top:
        top_df = pd.DataFrame(top, columns=["Task ID", "Note Count"]).set_index("Task ID")
        st.bar_chart(top_df)


def _render_tool_call_frequency(data: dict) -> None:
    st.subheader(f"Tool Call Frequency (last {_TOOL_WINDOW_DAYS} days)")
    tool_freq: dict[str, int] = data["tool_freq"]
    if not tool_freq:
        st.info("No tool calls recorded in the last 30 days.")
        return
    freq_df = pd.DataFrame(
        {"tool": list(tool_freq.keys()), "calls": list(tool_freq.values())}
    ).set_index("tool")
    st.bar_chart(freq_df)


def main() -> None:
    st.set_page_config(page_title="Wizard Dashboard", layout="wide")
    st.title("Wizard Health Dashboard")
    now = datetime.datetime.now().strftime("%H:%M:%S")
    st.caption(f"Refreshed at {now} — auto-refresh every 30s")
    data = _load_dashboard_data()
    _render_active_session(data)
    st.divider()
    _render_recent_notes(data)
    st.divider()
    _render_synthesis_health(data)
    st.divider()
    _render_memory_utilisation(data)
    st.divider()
    _render_tool_call_frequency(data)
    time.sleep(30)
    st.rerun()


main()
