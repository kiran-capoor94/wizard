"""Notes explorer page."""

import streamlit as st

from wizard.database import get_session
from wizard.repositories.note import NoteRepository

_notes = NoteRepository()

_DAY_OPTIONS = [7, 14, 30, 90]
_TYPE_OPTIONS = ["All", "observation", "decision", "blocker", "investigation", "mental_model"]


def render() -> None:
    st.title("Notes")

    col1, col2 = st.columns(2)
    days = col1.selectbox("Window", _DAY_OPTIONS, format_func=lambda d: f"Last {d} days")
    note_type = col2.selectbox("Type", _TYPE_OPTIONS)

    with get_session() as db:
        rows = _notes.get_recent(db, days=days)

    if note_type != "All":
        def _ntype(n) -> str:  # noqa: ANN001
            return n.note_type.value if hasattr(n.note_type, "value") else str(n.note_type)
        rows = [n for n in rows if _ntype(n) == note_type]

    if not rows:
        st.info("No notes in the selected window.")
        return

    st.caption(f"{len(rows)} note(s)")

    for note in rows:
        ntype = note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type)
        ts = note.created_at.strftime("%Y-%m-%d %H:%M") if note.created_at else ""
        label = f"`{ntype}` — {ts}"
        with st.expander(label, expanded=False):
            st.write(note.content)
            if note.mental_model:
                st.caption(f"Mental model: {note.mental_model}")
            if note.task_id:
                st.caption(f"Task ID: {note.task_id}")
            if note.session_id:
                st.caption(f"Session ID: {note.session_id}")
            st.caption(f"Status: {note.status}")
