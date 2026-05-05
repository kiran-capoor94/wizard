"""Search page — hybrid BM25 + cosine search across all entity types."""

import streamlit as st

from wizard.database import get_session
from wizard.repositories.search import SearchRepository

_search = SearchRepository()

_ENTITY_OPTIONS = ["All", "note", "task", "session", "meeting"]
_LIMIT = 30


def render() -> None:
    st.title("Search")

    col1, col2 = st.columns([3, 1])
    query = col1.text_input("Query", placeholder="e.g. auth middleware error")
    entity_type = col2.selectbox("Entity type", _ENTITY_OPTIONS)

    if not query.strip():
        st.info("Enter a query to search across notes, tasks, sessions, and meetings.")
        return

    etype = None if entity_type == "All" else entity_type

    with get_session() as db:
        results = _search.hybrid_search(db, query.strip(), limit=_LIMIT, entity_type=etype)  # type: ignore[arg-type]

    if not results:
        st.warning("No results found.")
        return

    st.caption(f"{len(results)} result(s)")

    for r in results:
        date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else ""
        label = f"`{r.entity_type}` **{r.title}** - {date_str}"
        with st.expander(label, expanded=False):
            st.write(r.snippet or "_no preview_")
            if r.task_id:
                st.caption(f"Task ID: {r.task_id}")
