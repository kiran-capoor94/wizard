"""SearchRepository — hybrid BM25+cosine search across notes, sessions, meetings, tasks."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime
from typing import Literal

from sqlalchemy import text
from sqlmodel import Session

from ..embedding import embed, serialize_float32
from ..schemas import SearchResult

logger = logging.getLogger(__name__)

EntityType = Literal["note", "session", "meeting", "task"]

_ALPHA = 0.5  # weight for BM25; (1-_ALPHA) for cosine
_RRF_K = 60
_POOL_MULTIPLIER = 5
_VEC_MAX_DISTANCE = 0.8  # cosine distance (0-2); drop vec hits at/above this

_TERM_RE = re.compile(r"\w+", re.UNICODE)


def _build_fts_query(query: str) -> str:
    """Build an OR-of-prefix-terms FTS5 MATCH string from free text.

    Each word becomes a quoted prefix token ("foo"*) so FTS5 operators in
    user input are neutralised and partial-word matches are restored. Returns
    "" when no usable terms remain (caller treats that as empty -> []).
    """
    terms = _TERM_RE.findall(query)
    if not terms:
        return ""
    return " OR ".join(f'"{t}"*' for t in terms)


Key = tuple[str, int]  # (entity_type, entity_id)


def _rrf_fuse(lanes: list[list[Key]], k: int = _RRF_K) -> dict[Key, float]:
    """Reciprocal Rank Fusion: sum 1/(k + rank + 1) across lanes per key.

    Scale-free — combines BM25-rank and cosine-distance lanes without
    reconciling their score scales. A key in only one lane still scores > 0.
    """
    scores: dict[Key, float] = {}
    for lane in lanes:
        for rank, key in enumerate(lane):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    return scores


def bm25_score(rank: float) -> float:
    """Convert FTS5 rank (negative, lower=better) to 0-1 score (higher=better)."""
    strength = max(0.0, -rank)
    return strength / (1.0 + strength)


def cosine_score(distance: float) -> float:
    """Convert vec0 cosine distance (0-2) to 0-1 score (higher=better)."""
    return 1.0 - distance / 2.0


class SearchRepository:
    def hybrid_search(
        self,
        db: Session,
        query: str,
        limit: int = 10,
        entity_type: EntityType | None = None,
    ) -> list[SearchResult]:
        """Hybrid BM25+cosine search. Notes blend both; other entities use BM25 only."""
        sanitised = query.replace('"', "").replace("*", "").strip()
        if not sanitised:
            return []
        fts_query = f'"{sanitised}"'
        query_vec = embed(query)
        results: list[tuple[float, SearchResult]] = []

        if entity_type is None or entity_type == "note":
            results.extend(self._search_notes(db, fts_query, query_vec, limit))
        if entity_type is None or entity_type == "session":
            results.extend(self._search_sessions(db, fts_query, limit))
        if entity_type is None or entity_type == "meeting":
            results.extend(self._search_meetings(db, fts_query, limit))
        if entity_type is None or entity_type == "task":
            results.extend(self._search_tasks(db, fts_query, limit))

        results.sort(key=lambda x: x[0], reverse=True)  # higher score = better
        return [r for _, r in results[:limit]]

    def _search_notes(
        self,
        db: Session,
        fts_query: str,
        query_vec: list[float] | None,
        limit: int,
    ) -> list[tuple[float, SearchResult]]:
        # BM25 lane
        bm25_rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT note_fts.rowid AS entity_id, note_fts.content AS content, "
                "note_fts.note_type AS note_type, note.task_id AS task_id, "
                "note.created_at AS created_at, note_fts.rank AS rank "
                "FROM note_fts "
                "JOIN note ON note.id = note_fts.rowid "
                "WHERE note_fts MATCH :q "
                "ORDER BY note_fts.rank LIMIT :lim"
            ),
            {"q": fts_query, "lim": limit},
        ).mappings().fetchall()

        bm25_scores: dict[int, float] = {
            row["entity_id"]: bm25_score(row["rank"]) for row in bm25_rows
        }
        bm25_meta: dict[int, dict] = {
            row["entity_id"]: dict(row) for row in bm25_rows
        }

        # Cosine lane (only when embedding is available)
        cosine_scores: dict[int, float] = {}
        if query_vec is not None:
            blob = serialize_float32(query_vec)
            try:
                vec_rows = db.execute(  # type: ignore[call-overload]
                    text(
                        "SELECT note_id, distance "
                        "FROM vec_note_embeddings "
                        "WHERE embedding MATCH :blob "
                        "ORDER BY distance LIMIT :lim"
                    ),
                    {"blob": blob, "lim": limit},
                ).mappings().fetchall()
                cosine_scores = {
                    row["note_id"]: cosine_score(row["distance"]) for row in vec_rows
                }
            except Exception as e:
                logger.warning(
                    "Cosine search failed, falling back to BM25-only: %s", e
                )

        # BM25 anchors candidate set; cosine re-ranks but cannot surface new notes
        out = []
        for note_id, b in bm25_scores.items():
            c = cosine_scores.get(note_id, 0.0)
            score = _ALPHA * b + (1.0 - _ALPHA) * c
            meta = bm25_meta[note_id]
            snippet = (meta.get("content") or "")[:200]
            out.append((
                score,
                SearchResult(
                    entity_type="note",
                    entity_id=note_id,
                    title=meta.get("note_type") or "note",
                    snippet=snippet,
                    created_at=meta.get("created_at"),
                    task_id=meta.get("task_id"),
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
                bm25_score(row["rank"]),
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
                bm25_score(row["rank"]),
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
                bm25_score(row["rank"]),
                SearchResult(
                    entity_type="task",
                    entity_id=row["entity_id"],
                    title=row["name"] or "task",
                    snippet=row["name"] or "",
                    created_at=row["created_at"],
                ),
            ))
        return out
