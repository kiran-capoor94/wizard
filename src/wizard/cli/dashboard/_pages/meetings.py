"""Meetings explorer page."""

import streamlit as st

from wizard.database import get_session
from wizard.repositories.meeting import MeetingRepository

_meetings = MeetingRepository()

_PAGE_SIZE = 30


def render() -> None:
    st.title("Meetings")

    if "meetings_offset" not in st.session_state:
        st.session_state["meetings_offset"] = 0

    offset = st.session_state["meetings_offset"]

    with get_session() as db:
        rows = _meetings.list_paginated(db, limit=_PAGE_SIZE, offset=offset)
        total = _meetings.count(db)

    if not rows:
        st.info("No meetings recorded yet.")
        return

    st.caption(f"{total} total meeting(s)")

    for meeting in rows:
        ts = meeting.created_at.strftime("%Y-%m-%d") if meeting.created_at else ""
        mc = meeting.category
        cat = mc.value if hasattr(mc, "value") else str(mc)
        label = f"**{meeting.title}** — {ts} `{cat}`"
        with st.expander(label, expanded=False):
            if meeting.summary:
                st.write(meeting.summary)
            else:
                st.caption("_No summary_")
            if meeting.source_url:
                st.markdown(f"[Source]({meeting.source_url})")
            st.caption(f"ID: {meeting.id} · Source: {meeting.source_type or '—'}")

    c1, c2, _ = st.columns([1, 1, 4])
    if offset > 0 and c1.button("← Prev"):
        st.session_state["meetings_offset"] = max(0, offset - _PAGE_SIZE)
        st.rerun()
    if len(rows) == _PAGE_SIZE and c2.button("Next →"):
        st.session_state["meetings_offset"] = offset + _PAGE_SIZE
        st.rerun()
