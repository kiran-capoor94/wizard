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
        sanitised = query.replace('"', "").replace("*", "").strip()
        if not sanitised:
            return []
        fts_query = f'"{sanitised}"'
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
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT note_fts.rowid AS entity_id, note_fts.content AS content, "
                "note_fts.note_type AS note_type, note.task_id AS task_id, "
                "note.created_at AS created_at, note_fts.rank AS rank "
                "FROM note_fts "
                "JOIN note ON note.id = note_fts.rowid "
                "WHERE note_fts MATCH :q "
                "ORDER BY note_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).mappings().fetchall()
        out = []
        for row in rows:
            snippet = (row["content"] or "")[:200]
            out.append((
                row["rank"],
                SearchResult(
                    entity_type="note",
                    entity_id=row["entity_id"],
                    title=row["note_type"] or "note",
                    snippet=snippet,
                    created_at=row["created_at"],
                    task_id=row["task_id"],
                ),
            ))
        return out

    def _search_sessions(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT session_fts.rowid AS entity_id, session_fts.summary AS summary, "
                "wizardsession.created_at AS created_at, session_fts.rank AS rank "
                "FROM session_fts "
                "JOIN wizardsession ON wizardsession.id = session_fts.rowid "
                "WHERE session_fts MATCH :q "
                "ORDER BY session_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).mappings().fetchall()
        out = []
        for row in rows:
            snippet = (row["summary"] or "")[:200]
            created = row["created_at"]
            title = f"Session {row['entity_id']}"
            if created:
                with contextlib.suppress(ValueError):
                    title = f"Session {datetime.fromisoformat(str(created)).strftime('%Y-%m-%d')}"
            out.append((
                row["rank"],
                SearchResult(
                    entity_type="session",
                    entity_id=row["entity_id"],
                    title=title,
                    snippet=snippet,
                    created_at=row["created_at"],
                ),
            ))
        return out

    def _search_meetings(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT meeting_fts.rowid AS entity_id, meeting_fts.content AS content, "
                "meeting_fts.title AS title, meeting.created_at AS created_at, "
                "meeting_fts.rank AS rank "
                "FROM meeting_fts "
                "JOIN meeting ON meeting.id = meeting_fts.rowid "
                "WHERE meeting_fts MATCH :q "
                "ORDER BY meeting_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).mappings().fetchall()
        out = []
        for row in rows:
            snippet = (row["content"] or "")[:200]
            out.append((
                row["rank"],
                SearchResult(
                    entity_type="meeting",
                    entity_id=row["entity_id"],
                    title=row["title"] or "meeting",
                    snippet=snippet,
                    created_at=row["created_at"],
                ),
            ))
        return out

    def _search_tasks(
        self, db: Session, query: str, limit: int
    ) -> list[tuple[float, SearchResult]]:
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT task_fts.rowid AS entity_id, task_fts.name AS name, "
                "task.created_at AS created_at, task_fts.rank AS rank "
                "FROM task_fts "
                "JOIN task ON task.id = task_fts.rowid "
                "WHERE task_fts MATCH :q "
                "ORDER BY task_fts.rank LIMIT :lim"
            ),
            {"q": query, "lim": limit},
        ).mappings().fetchall()
        out = []
        for row in rows:
            out.append((
                row["rank"],
                SearchResult(
                    entity_type="task",
                    entity_id=row["entity_id"],
                    title=row["name"] or "task",
                    snippet=row["name"] or "",
                    created_at=row["created_at"],
                ),
            ))
        return out
