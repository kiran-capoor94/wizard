"""Sidebar nav rail with collapsible icon-only mode."""

import streamlit as st

_NAV_ITEMS = [
    ("home", "🏠", "Home"),
    ("tasks", "✅", "Tasks"),
    ("notes", "📝", "Notes"),
    ("sessions", "🕐", "Sessions"),
    ("meetings", "🗓", "Meetings"),
    ("artifacts", "📦", "Artifacts"),
    ("search", "🔍", "Search"),
    ("health", "❤️", "Health"),
]

_BOTTOM_ITEMS = [
    ("raw_query", "🗄️", "Raw Query"),
]


def render() -> str:
    """Render the sidebar nav rail. Returns the currently active page key."""
    if "page" not in st.session_state:
        st.session_state["page"] = "home"
    if "sidebar_collapsed" not in st.session_state:
        st.session_state["sidebar_collapsed"] = False

    collapsed = st.session_state["sidebar_collapsed"]

    with st.sidebar:
        toggle_label = "›" if collapsed else "‹"
        if st.button(toggle_label, key="sidebar_toggle", help="Toggle sidebar"):
            st.session_state["sidebar_collapsed"] = not collapsed
            st.rerun()

        if not collapsed:
            st.markdown("**🧙 Wizard**")
        st.divider()

        for key, icon, label in _NAV_ITEMS:
            display = icon if collapsed else f"{icon} {label}"
            active = st.session_state["page"] == key
            if st.button(
                display,
                key=f"nav_{key}",
                help=label if collapsed else None,
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                st.session_state["page"] = key
                st.rerun()

        st.divider()

        for key, icon, label in _BOTTOM_ITEMS:
            display = icon if collapsed else f"{icon} {label}"
            active = st.session_state["page"] == key
            if st.button(
                display,
                key=f"nav_{key}",
                help=label if collapsed else None,
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                st.session_state["page"] = key
                st.rerun()

    return st.session_state["page"]
