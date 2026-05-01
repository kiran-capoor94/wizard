"""SearchRepository — FTS5 full-text search across notes, sessions, meetings, tasks."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import Literal

from sqlalchemy import text
from sqlmodel import Session

from ..schemas import SearchResult

logger = logging.getLogger(__name__)

EntityType = Literal["note", "session", "meeting", "task"]


class SearchRepository:
    def search(
        self,
        db: Session,
        query: str,
        limit: int = 10,
        entity_type: EntityType | None = None,
    ) -> list[SearchResult]:
        """Fan out across FTS5 tables, merge, sort by rank, return top results."""
        # Wrap in double-quotes so FTS5 treats the whole phrase literally,
        # avoiding mis-parsing of hyphens and special characters as operators.
        fts_query = f'"{query.replace(chr(34), "")}"'
        results: list[tuple[float, SearchResult]] = []

        if entity_type is None or entity_type == "note":
            results.extend(self._search_notes(db, fts_query, limit))
        if entity_type is None or entity_type == "session":
            results.extend(self._search_sessions(db, fts_query, limit))
        if entity_type is None or entity_type == "meeting":
            results.extend(self._search_meetings(db, fts_query, limit))
        if entity_type is None or entity_type == "task":
            results.extend(self._search_tasks(db, fts_query, limit))

        results.sort(key=lambda x: x[0])  # FTS5 rank: lower = better match
        return [r for _, r in results[:limit]]

    def _search_notes(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(
            text(
                "SELECT note_fts.rowid, note_fts.content, note_fts.note_type, "
                "note.task_id, note.created_at, note_fts.rank "
                "FROM note_fts "
                "JOIN note ON note.id = note_fts.rowid "
                "WHERE note_fts MATCH :q "
                "ORDER BY note_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).fetchall()
        out = []
        for row in rows:
            snippet = (row[1] or "")[:200]
            out.append((
                row[5],
                SearchResult(
                    entity_type="note",
                    entity_id=row[0],
                    title=row[2] or "note",
                    snippet=snippet,
                    created_at=row[4],
                    task_id=row[3],
                ),
            ))
        return out

    def _search_sessions(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(
            text(
                "SELECT session_fts.rowid, session_fts.summary, "
                "wizardsession.created_at, session_fts.rank "
                "FROM session_fts "
                "JOIN wizardsession ON wizardsession.id = session_fts.rowid "
                "WHERE session_fts MATCH :q "
                "ORDER BY session_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).fetchall()
        out = []
        for row in rows:
            snippet = (row[1] or "")[:200]
            created = row[2]
            title = f"Session {row[0]}"
            if created:
                with contextlib.suppress(ValueError):
                    title = f"Session {datetime.fromisoformat(str(created)).strftime('%Y-%m-%d')}"
            out.append((
                row[3],
                SearchResult(
                    entity_type="session",
                    entity_id=row[0],
                    title=title,
                    snippet=snippet,
                    created_at=row[2],
                ),
            ))
        return out

    def _search_meetings(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(
            text(
                "SELECT meeting_fts.rowid, meeting_fts.content, meeting_fts.title, "
                "meeting.created_at, meeting_fts.rank "
                "FROM meeting_fts "
                "JOIN meeting ON meeting.id = meeting_fts.rowid "
                "WHERE meeting_fts MATCH :q "
                "ORDER BY meeting_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).fetchall()
        out = []
        for row in rows:
            snippet = (row[1] or "")[:200]
            out.append((
                row[4],
                SearchResult(
                    entity_type="meeting",
                    entity_id=row[0],
                    title=row[2] or "meeting",
                    snippet=snippet,
                    created_at=row[3],
                ),
            ))
        return out

    def _search_tasks(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(
            text(
                "SELECT task_fts.rowid, task_fts.name, task.created_at, task_fts.rank "
                "FROM task_fts "
                "JOIN task ON task.id = task_fts.rowid "
                "WHERE task_fts MATCH :q "
                "ORDER BY task_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).fetchall()
        out = []
        for row in rows:
            out.append((
                row[3],
                SearchResult(
                    entity_type="task",
                    entity_id=row[0],
                    title=row[1] or "task",
                    snippet=row[1] or "",
                    created_at=row[2],
                ),
            ))
        return out
