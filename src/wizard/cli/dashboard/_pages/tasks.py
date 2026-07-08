"""Tasks explorer page."""

import pandas as pd
import streamlit as st

from wizard.database import get_session
from wizard.repositories.task import TaskRepository

_tasks = TaskRepository()

_PAGE_SIZE = 50
_STATUS_OPTIONS = ["All", "todo", "in_progress", "blocked", "done"]


def render() -> None:
    st.title("Tasks")

    col1, col2, col3 = st.columns([2, 2, 1])
    # Explicit keys so Reset can actually clear them — without a key, a widget's
    # value lives in Streamlit's own per-widget state and st.rerun() alone
    # (the previous implementation) leaves it completely untouched.
    status_filter = col1.selectbox("Status", _STATUS_OPTIONS, key="tasks_status_filter")
    source_filter = col2.text_input(
        "Source type", placeholder="JIRA, NOTION…", key="tasks_source_filter"
    )
    if col3.button("Reset"):
        st.session_state.pop("tasks_status_filter", None)
        st.session_state.pop("tasks_source_filter", None)
        st.session_state["tasks_offset"] = 0
        st.rerun()

    if "tasks_offset" not in st.session_state:
        st.session_state["tasks_offset"] = 0

    status_list = None if status_filter == "All" else [status_filter]
    source = source_filter.strip() or None

    with get_session() as db:
        rows = _tasks.list_paginated(
            db,
            status_filter=status_list,
            source_type_filter=source,
            limit=_PAGE_SIZE,
            offset=st.session_state["tasks_offset"],
        )

    if not rows:
        st.info("No tasks match the current filters.")
        return

    df = pd.DataFrame([
        {
            "ID": t.id,
            "Name": t.name,
            "Status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "Priority": t.priority.value if hasattr(t.priority, "value") else str(t.priority),
            "Category": t.category.value if hasattr(t.category, "value") else str(t.category),
            "Source": t.source_type or "—",
            "Due": t.due_date.strftime("%Y-%m-%d") if t.due_date else "—",
        }
        for t in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    offset = st.session_state["tasks_offset"]
    c1, c2, _ = st.columns([1, 1, 4])
    if offset > 0 and c1.button("← Prev"):
        st.session_state["tasks_offset"] = max(0, offset - _PAGE_SIZE)
        st.rerun()
    if len(rows) == _PAGE_SIZE and c2.button("Next →"):
        st.session_state["tasks_offset"] = offset + _PAGE_SIZE
        st.rerun()
