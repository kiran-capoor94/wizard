"""Wizard dashboard — entry point and page router."""

from pathlib import Path

import streamlit as st

from wizard.cli.dashboard._pages import health, home
from wizard.config import settings


def _coming_soon() -> None:
    st.info("Coming in sub-project 2.")


def main() -> None:
    st.set_page_config(page_title="Wizard", layout="wide", page_icon="🧙")

    if not Path(settings.db).exists() and settings.db != ":memory:":
        st.error("Database not found. Run 'wizard setup' first.")
        st.stop()

    pg = st.navigation(
        {
            "": [
                st.Page(home.render, title="Home", icon="🏠", default=True),
            ],
            "Data": [
                st.Page(_coming_soon, title="Tasks", icon="✅", url_path="tasks"),
                st.Page(_coming_soon, title="Notes", icon="📝", url_path="notes"),
                st.Page(_coming_soon, title="Sessions", icon="🕐", url_path="sessions"),
                st.Page(_coming_soon, title="Meetings", icon="🗓", url_path="meetings"),
                st.Page(_coming_soon, title="Artifacts", icon="📦", url_path="artifacts"),
                st.Page(_coming_soon, title="Search", icon="🔍", url_path="search"),
            ],
            "System": [
                st.Page(health.render, title="Health", icon="❤️"),
                st.Page(_coming_soon, title="Raw Query", icon="🗄️", url_path="raw-query"),
            ],
        }
    )
    pg.run()


main()
