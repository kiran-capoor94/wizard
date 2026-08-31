"""GraphMemoryService — maps Wizard entities to Graphiti episodes and
orchestrates Graphiti-primary / SQLite-fallback search."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from .exceptions import GraphitiUnavailable
from .integrations.graphiti import GraphitiClient
from .schemas import SearchResult

logger = logging.getLogger(__name__)

# "task" excluded: tasks are never written to Graphiti, so recognizing the
# type here would make task hits silently unfindable in graphiti-mode.
_VALID_TYPES = {"note", "session", "meeting"}


def episode_uuid(entity_type: str, entity_id: int) -> str:
    return f"wizard-{entity_type}-{entity_id}"


def parse_episode_uuid(uuid: str) -> tuple[str, int] | None:
    parts = uuid.split("-", 2)
    if len(parts) != 3 or parts[0] != "wizard" or parts[1] not in _VALID_TYPES:
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


def note_body(
    note_type: str, content: str, mental_model: str | None,
    task_id: int | None, session_id: int | None, supersedes_note_id: int | None,
) -> str:
    return json.dumps({
        "kind": "note", "id": None, "note_type": note_type, "content": content,
        "mental_model": mental_model, "task_id": task_id, "session_id": session_id,
        "supersedes": episode_uuid("note", supersedes_note_id) if supersedes_note_id else None,
    })


def session_body(
    intent: str, state_delta: str, open_loops: list[str],
    next_actions: list[str], closure_status: str,
) -> str:
    return json.dumps({
        "kind": "session", "intent": intent, "state_delta": state_delta,
        "open_loops": open_loops, "next_actions": next_actions,
        "closure_status": closure_status,
    })


def meeting_body(title: str, category: str, content: str, summary: str | None) -> str:
    return json.dumps({
        "kind": "meeting", "title": title, "category": category,
        "content": content, "summary": summary,
    })


def _parse_ts(value: str | None) -> datetime | None:
    """Safely parse an ISO timestamp string. Returns None on missing/unparseable
    input rather than raising — a bad timestamp must not break search."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def fact_to_search_result(fact: dict) -> SearchResult:
    """Map a Graphiti /search fact dict to a fact-level SearchResult.

    Facts are graph-extracted edges, not Wizard rows — entity_id is None.
    """
    return SearchResult(
        entity_type="fact",
        entity_id=None,
        title=fact.get("name") or "fact",
        snippet=fact.get("fact") or "",
        created_at=_parse_ts(fact.get("valid_at") or fact.get("created_at")),
    )


class GraphMemoryService:
    """Dual-writes Wizard entities to Graphiti and caches reachability checks."""

    def __init__(
        self, client: GraphitiClient, enabled: bool, health_ttl_seconds: float = 30.0
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._ttl = health_ttl_seconds
        self._reachable_cache: tuple[float, bool] | None = None

    def push_episode(
        self, entity_type: str, entity_id: int, body: str,
        reference_time: datetime,
    ) -> None:
        # The episode name IS the namespaced identity — it is the only
        # deterministic field Graphiti persists for us (uuid cannot be sent;
        # see GraphitiClient.add_episode).
        if not self._enabled:
            return
        try:
            self._client.add_episode(
                name=episode_uuid(entity_type, entity_id),
                body=body, reference_time=reference_time,
                source_description=f"wizard:{entity_type}",
            )
        except GraphitiUnavailable as e:
            logger.warning("Graphiti dual-write skipped (%s): %s", entity_type, e)

    def is_reachable(self) -> bool:
        if not self._enabled:
            return False
        now = time.monotonic()
        if self._reachable_cache and now - self._reachable_cache[0] < self._ttl:
            return self._reachable_cache[1]
        try:
            ok = self._client.health()
        except GraphitiUnavailable:
            ok = False
        self._reachable_cache = (now, ok)
        return ok

    def search(
        self, db, query: str, limit: int, entity_type: str | None, search_repo,
    ) -> list[SearchResult]:
        if not self.is_reachable():
            return search_repo.hybrid_search(db, query, limit=limit, entity_type=entity_type)
        try:
            facts = self._client.search(query, limit)
        except GraphitiUnavailable as e:
            logger.warning("Graphiti search failed, falling back to SQLite: %s", e)
            return search_repo.hybrid_search(db, query, limit=limit, entity_type=entity_type)
        return [fact_to_search_result(f) for f in facts][:limit]
