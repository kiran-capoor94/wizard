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
from wizard.repositories.session import SessionRepository
from wizard.repositories.task import TaskRepository

_analytics = AnalyticsRepository()
_sessions = SessionRepository()
_tasks = TaskRepository()

_NOTE_WINDOW_DAYS = 7
_TOOL_WINDOW_DAYS = 30
_SESSIONS_LIMIT = 30
_STALE_THRESHOLD = 3


def _load_dashboard_data() -> dict:
    if not Path(settings.db).exists() and settings.db != ":memory:":
        raise FileNotFoundError("Database not found. Run 'wizard setup' first.")
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=_NOTE_WINDOW_DAYS)
    month_ago = today - datetime.timedelta(days=_TOOL_WINDOW_DAYS)
    with get_session() as db:
        open_task_count = _tasks.count_open_tasks(db)
        sessions_today = _sessions.count_today(db)
        note_stats_7d = _analytics.get_note_stats(db, week_ago, today)
        session_stats_7d = _analytics.get_session_stats(db, week_ago, today)
        task_stats_7d = _analytics.get_task_stats(db, week_ago, today)
        compounding = _analytics.get_compounding_score(db, month_ago, today)
        tool_freq = _analytics.get_tool_call_frequency(db, days=_TOOL_WINDOW_DAYS)
        recent_sessions = _sessions.list_paginated(db, limit=_SESSIONS_LIMIT)
        recent_sessions_dicts = [
            {
                "id": s.id,
                "created_at": s.created_at,
                "closed_by": s.closed_by,
                "synthesis_status": s.synthesis_status,
            }
            for s in recent_sessions
        ]
        open_tasks = _tasks.get_open_task_contexts(db)
        open_tasks_dicts = [
            {
                "id": tc.id,
                "name": tc.name,
                "priority": (
                    tc.priority.value if hasattr(tc.priority, "value") else str(tc.priority)
                ),
                "status": tc.status.value if hasattr(tc.status, "value") else str(tc.status),
                "stale_days": tc.stale_days or 0,
                "note_count": tc.note_count or 0,
                "last_worked_at": tc.last_worked_at,
            }
            for tc in open_tasks
        ]
        blocked_tasks = _tasks.get_blocked_task_contexts(db)
        blocked_tasks_dicts = [
            {
                "id": tc.id,
                "name": tc.name,
                "priority": (
                    tc.priority.value if hasattr(tc.priority, "value") else str(tc.priority)
                ),
                "stale_days": tc.stale_days or 0,
                "note_count": tc.note_count or 0,
            }
            for tc in blocked_tasks
        ]
        note_velocity = _analytics.get_note_velocity(db, week_ago, today)
        session_velocity = _analytics.get_session_velocity(db, week_ago, today)
    return {
        "open_task_count": open_task_count,
        "sessions_today": sessions_today,
        "note_stats_7d": note_stats_7d,
        "session_stats_7d": session_stats_7d,
        "task_stats_7d": task_stats_7d,
        "compounding": compounding,
        "tool_freq": tool_freq,
        "recent_sessions": recent_sessions_dicts,
        "open_tasks": open_tasks_dicts,
        "blocked_tasks": blocked_tasks_dicts,
        "note_velocity": note_velocity,
        "session_velocity": session_velocity,
    }


def _render_kpi_strip(data: dict) -> None:
    ss = data["session_stats_7d"]
    synthesis_failures = ss["synthesis_failures"]
    synthesis_pct = (
        round((ss["session_count"] - synthesis_failures) / ss["session_count"] * 100)
        if ss["session_count"] > 0 else 100
    )
    stale = data["task_stats_7d"]["stale_count"]
    compounding_pct = round(data["compounding"] * 100)
    tool_calls_total = sum(data["tool_freq"].values())

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    col1.metric("Open Tasks", data["open_task_count"])
    col2.metric("Sessions Today", data["sessions_today"])
    col3.metric("Notes (7d)", data["note_stats_7d"]["total"])
    col4.metric(
        "Synthesis Health",
        f"{synthesis_pct}%",
        delta=f"-{synthesis_failures} failures" if synthesis_failures else None,
        delta_color="inverse",
    )
    col5.metric(
        "Stale Tasks",
        stale,
        delta=f"+{stale} needs attention" if stale > 5 else None,
        delta_color="inverse",
    )
    col6.metric(
        "Compounding Score",
        f"{compounding_pct}%",
        delta="low" if data["compounding"] < 0.5 else None,
        delta_color="inverse",
    )
    col7.metric("Tool Calls (30d)", tool_calls_total)


def _render_today_tab(data: dict) -> None:
    notes_today = data["note_velocity"].get(datetime.date.today().isoformat(), 0)
    col1, col2, col3 = st.columns(3)
    col1.metric("Sessions", data["sessions_today"])
    col2.metric("Notes Written", notes_today)
    col3.metric("Tool Calls (30d total)", sum(data["tool_freq"].values()))

    st.subheader("Top Tool Calls (30d)")
    if data["tool_freq"]:
        freq_df = (
            pd.DataFrame(data["tool_freq"].items(), columns=["Tool", "Calls"])
            .sort_values("Calls", ascending=False)
            .head(10)
        )
        st.dataframe(freq_df, use_container_width=True, hide_index=True)
    else:
        st.info("No tool calls recorded.")


def _render_week_tab(data: dict) -> None:
    st.subheader("Note Velocity (last 7 days)")
    velocity = data["note_velocity"]
    if any(v > 0 for v in velocity.values()):
        sorted_dates = sorted(velocity.keys())
        vel_df = pd.DataFrame(
            {"Date": sorted_dates, "Notes": [velocity[d] for d in sorted_dates]}
        ).set_index("Date")
        st.line_chart(vel_df)
    else:
        st.info("No notes in the last 7 days.")

    st.subheader("Avg Session Duration (last 7 days, minutes)")
    sdur = data["session_velocity"]
    if any(v > 0 for v in sdur.values()):
        sorted_sdur_dates = sorted(sdur.keys())
        sdur_df = pd.DataFrame(
            {"Date": sorted_sdur_dates, "Avg Duration (min)": [sdur[d] for d in sorted_sdur_dates]}
        ).set_index("Date")
        st.bar_chart(sdur_df)
    else:
        st.info("No session duration data for the last 7 days.")

    st.subheader("Session Summary (7d)")
    ss = data["session_stats_7d"]
    ts = data["task_stats_7d"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sessions", ss["session_count"])
    col2.metric("Avg Duration", f"{ss['avg_duration_minutes']} min")
    col3.metric("Abandoned", ss["abandoned_count"])
    col4.metric("Tasks Worked", ts["worked"])

    st.subheader("Note Breakdown by Type (7d)")
    by_type = data["note_stats_7d"]["by_type"]
    if by_type:
        nt_df = pd.DataFrame(by_type.items(), columns=["Type", "Count"]).set_index("Type")
        st.bar_chart(nt_df)


def _row_style(row: pd.Series) -> list[str]:
    if row["Stale Days"] >= _STALE_THRESHOLD:
        return ["background-color: #4a1c1c"] * len(row)
    raw = row.get("_last_worked_raw")
    if raw is not None and raw == datetime.date.today():
        return ["background-color: #1c3a1c"] * len(row)
    return [""] * len(row)


def _render_tasks_tab(data: dict) -> None:
    st.subheader("Open Tasks")
    tasks = data["open_tasks"]
    if tasks:
        df = pd.DataFrame([
            {
                "Name": t["name"],
                "Priority": t["priority"],
                "Status": t["status"],
                "Stale Days": t["stale_days"],
                "Notes": t["note_count"],
                "Last Touched": (
                    t["last_worked_at"].strftime("%Y-%m-%d") if t["last_worked_at"] else "—"
                ),
                # hidden sentinel — used by _row_style for date comparison, not rendered
                "_last_worked_raw": (
                    t["last_worked_at"].date() if t["last_worked_at"] else None
                ),
            }
            for t in tasks
        ])
        df = df.sort_values("Stale Days", ascending=False)
        styled = df.style.apply(_row_style, axis=1).hide(
            axis="columns", subset=["_last_worked_raw"]
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.success("No open tasks.")

    with st.expander(f"Blocked ({len(data['blocked_tasks'])} tasks)"):
        if data["blocked_tasks"]:
            blocked_df = pd.DataFrame([
                {
                    "Name": t["name"],
                    "Priority": t["priority"],
                    "Stale Days": t["stale_days"],
                    "Notes": t["note_count"],
                }
                for t in data["blocked_tasks"]
            ])
            st.dataframe(blocked_df, use_container_width=True, hide_index=True)
        else:
            st.info("No blocked tasks.")


def _render_health_tab(data: dict) -> None:
    st.subheader("Synthesis Failures (last 30 sessions)")
    sessions = data["recent_sessions"]
    failures = [s for s in sessions if s["synthesis_status"] == "partial_failure"]
    if failures:
        fail_df = pd.DataFrame([
            {
                "Session ID": s["id"],
                "Date": s["created_at"].strftime("%Y-%m-%d %H:%M"),
                "Closed By": s["closed_by"] or "open",
            }
            for s in failures
        ])
        st.dataframe(fail_df, use_container_width=True, hide_index=True)
    else:
        st.success("No synthesis failures in the last 30 sessions.")

    pending = [s for s in sessions if s["synthesis_status"] == "pending" and s["closed_by"]]
    if pending:
        st.warning(f"{len(pending)} closed session(s) with pending synthesis.")

    st.subheader("Session Close Method Breakdown")
    close_methods: dict[str, int] = {}
    for s in sessions:
        key = s["closed_by"] or "open"
        close_methods[key] = close_methods.get(key, 0) + 1
    if close_methods:
        cm_df = pd.DataFrame(close_methods.items(), columns=["Method", "Count"]).set_index("Method")
        st.bar_chart(cm_df)

    st.subheader(f"Tool Call Frequency (last {_TOOL_WINDOW_DAYS} days)")
    tool_freq = data["tool_freq"]
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
    ns = data["note_stats_7d"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Mental Model Coverage", f"{round(ns['mental_model_coverage'] * 100)}%")
    col2.metric("Unclassified Notes", ns["unclassified"])
    col3.metric("Superseded Notes", ns["superseded"])


def main() -> None:
    st.set_page_config(page_title="Wizard Dashboard", layout="wide")
    st.title("Wizard Dashboard")
    st.caption(
        f"Refreshed at {datetime.datetime.now().strftime('%H:%M:%S')} — auto-refresh every 60s"
    )
    try:
        data = _load_dashboard_data()
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
    _render_kpi_strip(data)
    st.divider()
    today_tab, week_tab, tasks_tab, health_tab = st.tabs(
        ["Today", "This Week", "Tasks", "Health"]
    )
    with today_tab:
        _render_today_tab(data)
    with week_tab:
        _render_week_tab(data)
    with tasks_tab:
        _render_tasks_tab(data)
    with health_tab:
        _render_health_tab(data)
    time.sleep(60)
    st.rerun()


main()
