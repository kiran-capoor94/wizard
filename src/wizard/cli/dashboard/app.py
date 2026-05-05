"""Wizard dashboard — entry point and page router."""

from pathlib import Path

import streamlit as st

from wizard.cli.dashboard.pages import health, home
from wizard.cli.dashboard.sidebar import render as render_sidebar
from wizard.config import settings

_PAGES = {
    "home": home.render,
    "health": health.render,
}

_CSS = """
<style>
[data-testid="stSidebar"] { min-width: 60px !important; max-width: 220px !important; }
[data-testid="stSidebarContent"] { padding: 0.5rem 0.25rem; }
</style>
"""


def main() -> None:
    st.set_page_config(page_title="Wizard", layout="wide", page_icon="🧙")
    st.markdown(_CSS, unsafe_allow_html=True)

    if not Path(settings.db).exists() and settings.db != ":memory:":
        st.error("Database not found. Run 'wizard setup' first.")
        st.stop()

    page_key = render_sidebar()
    page_fn = _PAGES.get(page_key)

    if page_fn is not None:
        page_fn()
    else:
        st.info(f"**{page_key.replace('_', ' ').title()}** — coming in sub-project 2.")


main()
