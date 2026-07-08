"""Raw Query page — execute arbitrary SQL against the local Wizard database."""

import pandas as pd
import streamlit as st
from sqlalchemy import text

from wizard.database import get_session

_EXAMPLE = "SELECT id, name, status FROM task ORDER BY id DESC LIMIT 20"


def render() -> None:
    st.title("Raw Query")
    st.caption(
        "Execute SQL directly against the local Wizard SQLite database. Read-only — "
        "enforced by SQLite's query_only pragma, not just convention."
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
            # SQLite rejects any INSERT/UPDATE/DELETE/DDL on this connection while
            # this is set — actual enforcement, since a text-box SQL query can't be
            # trusted to just be a SELECT no matter what the caption says.
            db.exec(text("PRAGMA query_only = ON"))
            try:
                result = db.exec(text(stripped))  # type: ignore[arg-type]
                rows = result.fetchall()
                keys = list(result.keys()) if hasattr(result, "keys") else []
            finally:
                db.exec(text("PRAGMA query_only = OFF"))
    except Exception as exc:
        st.error(f"Query error: {exc}")
        return

    if not rows:
        st.info("Query returned no rows.")
        return

    df = pd.DataFrame(rows, columns=keys) if keys else pd.DataFrame(rows)
    st.caption(f"{len(rows)} row(s)")
    st.dataframe(df, use_container_width=True)
