"""Sessions explorer page."""

import pandas as pd
import streamlit as st

from wizard.database import get_session
from wizard.repositories.note import NoteRepository
from wizard.repositories.session import SessionRepository
from wizard.repositories.task import TaskRepository

_sessions = SessionRepository()
_notes = NoteRepository()
_tasks = TaskRepository()

_PAGE_SIZE = 30
_CLOSURE_OPTIONS = ["All", "user", "hook", "auto"]


def render() -> None:
    st.title("Sessions")

    col1, col2 = st.columns([2, 1])
    closure_filter = col1.selectbox("Closed by", _CLOSURE_OPTIONS)

    if "sessions_offset" not in st.session_state:
        st.session_state["sessions_offset"] = 0

    closure = None if closure_filter == "All" else closure_filter
    offset = st.session_state["sessions_offset"]

    with get_session() as db:
        rows = _sessions.list_paginated(
            db, closure_status_filter=closure, limit=_PAGE_SIZE, offset=offset
        )
        total = _sessions.count(db, closure_status_filter=closure)

    if not rows:
        st.info("No sessions match the current filter.")
        return

    st.caption(f"{total} total session(s)")

    df = pd.DataFrame([
        {
            "ID": s.id,
            "Created": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "—",
            "Closed By": s.closed_by or "open",
            "Agent": s.agent or "—",
            "Mode": s.active_mode or "—",
        }
        for s in rows
    ])
    event = st.dataframe(
        df, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
    )

    selected_rows = event.selection.get("rows", []) if event.selection else []
    if selected_rows:
        session = rows[selected_rows[0]]
        st.divider()
        st.subheader(f"Session #{session.id}")
        col_a, col_b = st.columns(2)
        col_a.markdown(f"**Summary:** {session.summary or '_none_'}")
        col_b.markdown(f"**Continued from:** {session.continued_from_id or '—'}")

        with get_session() as db:
            session_notes = _notes.list_for_session(db, session.id)
            task_ids = list({n.task_id for n in session_notes if n.task_id})
            task_contexts = {tc.id: tc for tc in _tasks.get_task_contexts_by_ids(db, task_ids)}

        st.caption(f"{len(session_notes)} note(s)")
        by_task: dict = {}
        for note in session_notes:
            by_task.setdefault(note.task_id, []).append(note)

        for task_id, task_notes in by_task.items():
            tc = task_contexts.get(task_id) if task_id else None
            st.markdown(f"**{tc.name if tc else 'No task'}**")
            for note in task_notes:
                nt = note.note_type
                ntype = nt.value if hasattr(nt, "value") else str(nt)
                ts = note.created_at.strftime("%H:%M:%S") if note.created_at else ""
                with st.expander(f"`{ntype}` {ts}", expanded=False):
                    st.write(note.content)
                    if note.mental_model:
                        st.caption(f"Mental model: {note.mental_model}")

    c1, c2, _ = st.columns([1, 1, 4])
    if offset > 0 and c1.button("← Prev"):
        st.session_state["sessions_offset"] = max(0, offset - _PAGE_SIZE)
        st.rerun()
    if len(rows) == _PAGE_SIZE and c2.button("Next →"):
        st.session_state["sessions_offset"] = offset + _PAGE_SIZE
        st.rerun()
