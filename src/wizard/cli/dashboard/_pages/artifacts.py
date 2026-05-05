"""Artifacts explorer page — notes grouped by artifact_id."""

import streamlit as st
from sqlmodel import select

from wizard.database import get_session
from wizard.models import Note

_PAGE_SIZE = 20


def render() -> None:
    st.title("Artifacts")
    st.caption(
        "Notes grouped by artifact identity (artifact_id). "
        "Each artifact represents a task, session, or meeting."
    )

    if "artifacts_offset" not in st.session_state:
        st.session_state["artifacts_offset"] = 0

    offset = st.session_state["artifacts_offset"]

    with get_session() as db:
        rows = list(
            db.exec(
                select(Note)
                .where(Note.artifact_id != None)  # noqa: E711
                .order_by(Note.artifact_id, Note.created_at)  # type: ignore[arg-type]
            ).all()
        )

    if not rows:
        st.info("No artifact-linked notes found.")
        return

    by_artifact: dict[str, list] = {}
    for note in rows:
        if note.artifact_id:
            by_artifact.setdefault(note.artifact_id, []).append(note)

    artifact_ids = list(by_artifact.keys())
    page_ids = artifact_ids[offset: offset + _PAGE_SIZE]

    st.caption(f"{len(artifact_ids)} artifact(s) total")

    for aid in page_ids:
        notes = by_artifact[aid]
        artifact_type = notes[0].artifact_type or "unknown"
        label = f"`{artifact_type}` {aid[:8]}... - {len(notes)} note(s)"
        with st.expander(label, expanded=False):
            for note in notes:
                nt = note.note_type
                ntype = nt.value if hasattr(nt, "value") else str(nt)
                ts = note.created_at.strftime("%Y-%m-%d %H:%M") if note.created_at else ""
                st.markdown(f"**`{ntype}`** {ts}")
                st.write(note.content)
                if note.mental_model:
                    st.caption(f"Mental model: {note.mental_model}")
                st.divider()

    c1, c2, _ = st.columns([1, 1, 4])
    if offset > 0 and c1.button("<- Prev"):
        st.session_state["artifacts_offset"] = max(0, offset - _PAGE_SIZE)
        st.rerun()
    if offset + _PAGE_SIZE < len(artifact_ids) and c2.button("Next ->"):
        st.session_state["artifacts_offset"] = offset + _PAGE_SIZE
        st.rerun()
