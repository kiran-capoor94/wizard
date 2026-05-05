"""Wizard dashboard — entry point and page router."""

from pathlib import Path

import streamlit as st

from wizard.cli.dashboard._pages import (
    artifacts,
    health,
    home,
    meetings,
    notes,
    raw_query,
    search,
    sessions,
    tasks,
)
from wizard.config import settings


def main() -> None:
    st.set_page_config(page_title="Wizard", layout="wide", page_icon="🧙")

    if not Path(settings.db).exists() and settings.db != ":memory:":
        st.error("Database not found. Run 'wizard setup' first.")
        st.stop()

    pg = st.navigation(
        {
            "": [
                st.Page(home.render, title="Home", icon="🏠", default=True, url_path="home"),
            ],
            "Data": [
                st.Page(tasks.render, title="Tasks", icon="✅", url_path="tasks"),
                st.Page(notes.render, title="Notes", icon="📝", url_path="notes"),
                st.Page(sessions.render, title="Sessions", icon="🕐", url_path="sessions"),
                st.Page(meetings.render, title="Meetings", icon="🗓", url_path="meetings"),
                st.Page(artifacts.render, title="Artifacts", icon="📦", url_path="artifacts"),
                st.Page(search.render, title="Search", icon="🔍", url_path="search"),
            ],
            "System": [
                st.Page(health.render, title="Health", icon="❤️", url_path="health"),
                st.Page(raw_query.render, title="Raw Query", icon="🗄️", url_path="raw-query"),
            ],
        }
    )
    pg.run()


main()
