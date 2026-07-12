"""SearchRepository — hybrid BM25+cosine search across notes, sessions, meetings, tasks."""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import datetime
from typing import Literal

from sqlalchemy import bindparam, text
from sqlmodel import Session

from ..embedding import embed, serialize_float32
from ..schemas import SearchResult

logger = logging.getLogger(__name__)

EntityType = Literal["note", "session", "meeting", "task"]

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


class SearchRepository:
    def hybrid_search(
        self,
        db: Session,
        query: str,
        limit: int = 10,
        entity_type: EntityType | None = None,
    ) -> list[SearchResult]:
        """Union hybrid search: per-entity BM25 lanes + a threshold-gated cosine
        lane for notes, fused by Reciprocal Rank Fusion."""
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []
        query_vec = embed(query)
        pool = limit * _POOL_MULTIPLIER

        lanes: list[list[Key]] = []
        results: dict[Key, SearchResult] = {}

        def add(pair: tuple[list[list[Key]], dict[Key, SearchResult]]) -> None:
            new_lanes, new_results = pair
            lanes.extend(new_lanes)
            results.update(new_results)

        if entity_type in (None, "note"):
            add(self._search_notes(db, fts_query, query_vec, pool))
        if entity_type in (None, "session"):
            add(self._search_sessions(db, fts_query, pool))
        if entity_type in (None, "meeting"):
            add(self._search_meetings(db, fts_query, pool))
        if entity_type in (None, "task"):
            add(self._search_tasks(db, fts_query, pool))

        fused = _rrf_fuse(lanes)
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        return [results[key] for key, _ in ranked[:limit] if key in results]

    def _search_notes(
        self,
        db: Session,
        fts_query: str,
        query_vec: list[float] | None,
        pool: int,
    ) -> tuple[list[list[Key]], dict[Key, SearchResult]]:
        # BM25 lane: note ids in rank order.
        bm25_rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT note_fts.rowid AS entity_id "
                "FROM note_fts WHERE note_fts MATCH :q "
                "ORDER BY note_fts.rank LIMIT :lim"
            ),
            {"q": fts_query, "lim": pool},
        ).mappings().fetchall()
        bm25_ids = [row["entity_id"] for row in bm25_rows]

        # Cosine lane: note ids in distance order, threshold-gated. Degrades to
        # empty if embedding unavailable or vec table absent.
        vec_ids: list[int] = []
        if query_vec is not None:
            blob = serialize_float32(query_vec)
            try:
                vec_rows = db.execute(  # type: ignore[call-overload]
                    text(
                        "SELECT note_id, distance FROM vec_note_embeddings "
                        "WHERE embedding MATCH :blob ORDER BY distance LIMIT :lim"
                    ),
                    {"blob": blob, "lim": pool},
                ).mappings().fetchall()
                vec_ids = [
                    row["note_id"] for row in vec_rows
                    if row["distance"] < _VEC_MAX_DISTANCE
                ]
            except Exception as e:
                logger.warning("Cosine search failed, BM25-only for notes: %s", e)

        # Fetch metadata for the union of ids in one pass.
        all_ids: list[int] = list(dict.fromkeys(bm25_ids + vec_ids))
        meta: dict[int, dict] = {}
        if all_ids:
            meta_rows = db.execute(  # type: ignore[call-overload]
                text(
                    "SELECT id AS entity_id, content, note_type, task_id, created_at "
                    "FROM note WHERE id IN :ids AND status = 'active'"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": all_ids},
            ).mappings().fetchall()
            meta = {row["entity_id"]: dict(row) for row in meta_rows}

        results: dict[Key, SearchResult] = {}
        for nid in all_ids:
            m = meta.get(nid)
            if m is None:
                continue
            results[("note", nid)] = SearchResult(
                entity_type="note",
                entity_id=nid,
                title=m.get("note_type") or "note",
                snippet=(m.get("content") or "")[:200],
                created_at=m.get("created_at"),
                task_id=m.get("task_id"),
            )
        bm25_lane = [("note", i) for i in bm25_ids if i in meta]
        vec_lane = [("note", i) for i in vec_ids if i in meta]
        return [bm25_lane, vec_lane], results

    def _search_sessions(
        self, db: Session, fts_query: str, pool: int
    ) -> tuple[list[list[Key]], dict[Key, SearchResult]]:
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT session_fts.rowid AS entity_id, session_fts.summary AS summary, "
                "wizardsession.created_at AS created_at "
                "FROM session_fts JOIN wizardsession ON wizardsession.id = session_fts.rowid "
                "WHERE session_fts MATCH :q ORDER BY session_fts.rank LIMIT :lim"
            ),
            {"q": fts_query, "lim": pool},
        ).mappings().fetchall()
        lane: list[Key] = []
        results: dict[Key, SearchResult] = {}
        for row in rows:
            key: Key = ("session", row["entity_id"])
            created = row["created_at"]
            title = f"Session {row['entity_id']}"
            if created:
                with contextlib.suppress(ValueError):
                    title = f"Session {datetime.fromisoformat(str(created)).strftime('%Y-%m-%d')}"
            results[key] = SearchResult(
                entity_type="session", entity_id=row["entity_id"], title=title,
                snippet=(row["summary"] or "")[:200], created_at=created,
            )
            lane.append(key)
        return [lane], results

    def _search_meetings(
        self, db: Session, fts_query: str, pool: int
    ) -> tuple[list[list[Key]], dict[Key, SearchResult]]:
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT meeting_fts.rowid AS entity_id, meeting_fts.content AS content, "
                "meeting_fts.title AS title, meeting.created_at AS created_at "
                "FROM meeting_fts JOIN meeting ON meeting.id = meeting_fts.rowid "
                "WHERE meeting_fts MATCH :q ORDER BY meeting_fts.rank LIMIT :lim"
            ),
            {"q": fts_query, "lim": pool},
        ).mappings().fetchall()
        lane: list[Key] = []
        results: dict[Key, SearchResult] = {}
        for row in rows:
            key: Key = ("meeting", row["entity_id"])
            results[key] = SearchResult(
                entity_type="meeting", entity_id=row["entity_id"],
                title=row["title"] or "meeting", snippet=(row["content"] or "")[:200],
                created_at=row["created_at"],
            )
            lane.append(key)
        return [lane], results

    def _search_tasks(
        self, db: Session, fts_query: str, pool: int
    ) -> tuple[list[list[Key]], dict[Key, SearchResult]]:
        rows = db.execute(  # type: ignore[call-overload]
            text(
                "SELECT task_fts.rowid AS entity_id, task_fts.name AS name, "
                "task.created_at AS created_at "
                "FROM task_fts JOIN task ON task.id = task_fts.rowid "
                "WHERE task_fts MATCH :q ORDER BY task_fts.rank LIMIT :lim"
            ),
            {"q": fts_query, "lim": pool},
        ).mappings().fetchall()
        lane: list[Key] = []
        results: dict[Key, SearchResult] = {}
        for row in rows:
            key: Key = ("task", row["entity_id"])
            results[key] = SearchResult(
                entity_type="task", entity_id=row["entity_id"],
                title=row["name"] or "task", snippet=row["name"] or "",
                created_at=row["created_at"],
            )
            lane.append(key)
        return [lane], results
