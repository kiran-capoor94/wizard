"""Raw Query page — execute arbitrary SQL against the local Wizard database."""

import pandas as pd
import streamlit as st
from sqlalchemy import text

from wizard.database import get_session

_EXAMPLE = "SELECT id, name, status FROM task ORDER BY id DESC LIMIT 20"


def render() -> None:
    st.title("Raw Query")
    st.caption(
        "Execute SQL directly against the local Wizard SQLite database. Read-only by convention."
    )

    sql = st.text_area("SQL", value=_EXAMPLE, height=120)

    if not st.button("Run"):
        return

    stripped = sql.strip()
    if not stripped:
        st.warning("Enter a SQL query.")
        return

    try:
        with get_session() as db:
            result = db.exec(text(stripped))  # type: ignore[arg-type]
            rows = result.fetchall()
            keys = list(result.keys()) if hasattr(result, "keys") else []
    except Exception as exc:
        st.error(f"Query error: {exc}")
        return

    if not rows:
        st.info("Query returned no rows.")
        return

    df = pd.DataFrame(rows, columns=keys) if keys else pd.DataFrame(rows)
    st.caption(f"{len(rows)} row(s)")
    st.dataframe(df, use_container_width=True)
