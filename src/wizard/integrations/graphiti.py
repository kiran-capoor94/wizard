"""Thin HTTP client for the shared Graphiti graph service. No business logic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..exceptions import GraphitiUnavailable

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime) -> datetime:
    """Normalise to timezone-aware UTC.

    Wizard's SQLite timestamps come from datetime.now() — local and naive.
    Sent as-is, Graphiti stores a naive valid_at, and retrieve_episodes
    (which compares against an aware datetime.now(timezone.utc)) never matches
    them: GET /episodes returns [] for our partition, and add_episode's own
    previous-episodes lookup is always empty, so every episode is extracted
    with no prior context and no entity resolution against earlier ones.

    astimezone() reads a naive value as local — which is what it is — and
    converts; an already-aware value is just normalised.
    """
    return dt.astimezone(timezone.utc)


class GraphitiClient:
    def __init__(
        self,
        url: str,
        group_id: str,
        timeout_seconds: float,
        write_timeout_seconds: float | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._group_id = group_id
        self._read_timeout = timeout_seconds
        self._write_timeout = (
            write_timeout_seconds if write_timeout_seconds is not None else timeout_seconds
        )
        self._transport: httpx.BaseTransport | None = None  # test seam

    def _client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=self._url, timeout=timeout, transport=self._transport
        )

    def add_episode(
        self, name: str, body: str, reference_time: datetime,
        source_description: str,
    ) -> None:
        """Create an episode. `name` carries the namespaced identity
        (wizard-{type}-{id}); Graphiti persists it on the Episodic node.

        No uuid is sent. graphiti-core 0.22.0 reads add_episode(uuid=...) as
        "fetch this EXISTING episode" (graphiti.py:368 -> get_by_uuid) and
        raises NodeNotFoundError for a new one. That exception escapes
        graph_service's worker() and kills the single async ingest consumer
        for the life of the process, so every later POST /messages is 202'd
        into a queue nothing reads. /search returns edge uuids, never episode
        uuids, so a supplied uuid bought nothing on the read path either.
        """
        payload = {
            "group_id": self._group_id,
            "messages": [{
                "content": body, "role_type": "user", "role": "wizard",
                "name": name, "timestamp": _as_utc(reference_time).isoformat(),
                "source_description": source_description,
            }],
        }
        try:
            with self._client(self._write_timeout) as c:
                r = c.post("/messages", json=payload)
                r.raise_for_status()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e

    def existing_episode_names(self, limit: int) -> set[str]:
        """Episode names already in this group, for idempotent/resumable backfill.

        The episode `name` is our namespaced identity (wizard-{type}-{id});
        Graphiti generates its own uuids, so `name` is the only field we can
        match on. Requires timestamps to be tz-aware — see _as_utc.
        """
        try:
            with self._client(self._read_timeout) as c:
                r = c.get(f"/episodes/{self._group_id}", params={"last_n": limit})
                r.raise_for_status()
                episodes = r.json()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e
        return {e["name"] for e in episodes if e.get("name")}

    def search(self, query: str, limit: int) -> list[dict]:
        try:
            with self._client(self._read_timeout) as c:
                r = c.post("/search", json={
                    "query": query, "group_ids": [self._group_id], "max_facts": limit,
                })
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e
        return data.get("facts", [])

    def health(self) -> bool:
        try:
            with self._client(self._read_timeout) as c:
                r = c.get("/healthcheck")
                r.raise_for_status()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e
        return True
