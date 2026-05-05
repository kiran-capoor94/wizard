"""Home page — KPI left panel + activity feed with inline search."""

import datetime

import pandas as pd
import streamlit as st

from wizard.database import get_session
from wizard.repositories.analytics import AnalyticsRepository
from wizard.repositories.search import SearchRepository
from wizard.repositories.session import SessionRepository
from wizard.repositories.task import TaskRepository

_analytics = AnalyticsRepository()
_search = SearchRepository()
_sessions = SessionRepository()
_tasks = TaskRepository()

_NOTE_WINDOW_DAYS = 7
_STALE_RED = 3
_STALE_AMBER = 1
_FEED_PAGE_SIZE = 50
_TYPE_DOTS = {"session": "🔵", "note": "🟢", "task_event": "🟡"}


def _row_style(row: pd.Series) -> list[str]:
    if row["Stale Days"] > _STALE_RED:
        return ["background-color: #4a1c1c"] * len(row)
    if row["Stale Days"] >= _STALE_AMBER:
        return ["background-color: #3d2e00"] * len(row)
    if row.get("_touched_today"):
        return ["background-color: #1c3a1c"] * len(row)
    return [""] * len(row)


def _render_left_panel(db) -> None:
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=_NOTE_WINDOW_DAYS)
    month_ago = today - datetime.timedelta(days=30)

    open_task_count = _tasks.count_open_tasks(db)
    sessions_today = _sessions.count_today(db)
    session_stats = _analytics.get_session_stats(db, month_ago, today)
    open_tasks = _tasks.get_open_task_contexts(db)
    note_velocity = _analytics.get_note_velocity(db, week_ago, today)

    ss = session_stats
    synthesis_pct = (
        round((ss["session_count"] - ss["synthesis_failures"]) / ss["session_count"] * 100)
        if ss["session_count"] > 0 else 100
    )
    stale_count = sum(1 for t in open_tasks if (t.stale_days or 0) > _STALE_RED)

    col_a, col_b = st.columns(2)
    col_a.metric("Open Tasks", open_task_count)
    col_b.metric("Sessions Today", sessions_today)
    col_c, col_d = st.columns(2)
    col_c.metric(
        "Synthesis",
        f"{synthesis_pct}%",
        delta=f"-{ss['synthesis_failures']} fail" if ss["synthesis_failures"] else None,
        delta_color="inverse",
    )
    col_d.metric(
        "Stale Tasks",
        stale_count,
        delta=f"+{stale_count}" if stale_count > 0 else None,
        delta_color="inverse",
    )

    st.divider()
    st.caption("Open Tasks")
    top_tasks = sorted(open_tasks, key=lambda t: t.stale_days or 0, reverse=True)[:10]
    if top_tasks:
        tasks_df = pd.DataFrame([
            {
                "Name": t.name,
                "Status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "Stale Days": t.stale_days or 0,
                "_touched_today": (
                    t.last_worked_at is not None
                    and t.last_worked_at.date() == today
                ),
            }
            for t in top_tasks
        ])
        styled = tasks_df.style.apply(_row_style, axis=1).hide(
            axis="columns", subset=["_touched_today"]
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.success("No open tasks.")

    st.divider()
    st.caption("Notes / day (7d)")
    sorted_dates = sorted(note_velocity.keys())
    vel_df = pd.DataFrame({"Notes": [note_velocity[d] for d in sorted_dates]}, index=sorted_dates)
    st.bar_chart(vel_df, height=80)


def _render_search_results(results) -> None:
    if not results:
        st.warning("No results found.")
        return
    for r in results:
        date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else ""
        with st.expander(f"`{r.entity_type}` **{r.title}** — {date_str}", expanded=False):
            st.write(r.snippet or "_no preview_")
            if r.task_id:
                st.caption(f"Task ID: {r.task_id}")


def _render_activity_items(items, offset: int) -> None:
    if not items:
        st.info("No activity yet.")
        return

    for item in items:
        dot = _TYPE_DOTS.get(item.item_type, "⚪")
        ts = item.timestamp.strftime("%Y-%m-%d %H:%M") if item.timestamp else ""
        with st.expander(f"{dot} `{item.item_type}` **{item.title}** — {ts}", expanded=False):
            if item.subtitle:
                st.caption(item.subtitle)
            if item.detail:
                st.write(item.detail)

    if len(items) == _FEED_PAGE_SIZE and st.button("Load more"):
        st.session_state["feed_offset"] += _FEED_PAGE_SIZE
        st.rerun()


def _render_feed(db, query: str, entity_type: str | None) -> None:
    if "feed_offset" not in st.session_state:
        st.session_state["feed_offset"] = 0

    if query.strip():
        valid_types = {"note", "task", "session", "meeting"}
        etype = entity_type if entity_type in valid_types else None
        results = _search.hybrid_search(db, query.strip(), limit=_FEED_PAGE_SIZE, entity_type=etype)  # type: ignore[arg-type]
        _render_search_results(results)
        return

    offset = st.session_state["feed_offset"]
    items = _analytics.get_feed_items(db, offset=offset, limit=_FEED_PAGE_SIZE)
    _render_activity_items(items, offset)


def render() -> None:
    left, right = st.columns([1, 3])
    with get_session() as db:
        with left:
            _render_left_panel(db)
        with right:
            query = st.text_input(
                "Search",
                placeholder="Search notes, tasks, sessions…",
                label_visibility="collapsed",
            )
            entity_type = st.radio(
                "Type",
                ["All", "note", "task", "session", "meeting"],
                horizontal=True,
                label_visibility="collapsed",
            )
            etype = None if entity_type == "All" else entity_type
            _render_feed(db, query, etype)
