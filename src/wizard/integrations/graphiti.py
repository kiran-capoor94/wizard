"""Thin HTTP client for the shared Graphiti graph service. No business logic."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from ..exceptions import GraphitiUnavailable

logger = logging.getLogger(__name__)


class GraphitiClient:
    def __init__(self, url: str, group_id: str, timeout_seconds: float) -> None:
        self._url = url.rstrip("/")
        self._group_id = group_id
        self._timeout = timeout_seconds
        self._transport: httpx.BaseTransport | None = None  # test seam

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._url, timeout=self._timeout, transport=self._transport
        )

    def add_episode(
        self, name: str, body: str, reference_time: datetime,
        uuid: str, source_description: str,
    ) -> None:
        payload = {
            "group_id": self._group_id,
            "messages": [{
                "content": body, "role_type": "user", "role": "wizard",
                "name": name, "timestamp": reference_time.isoformat(),
                "source_description": source_description, "uuid": uuid,
            }],
        }
        try:
            with self._client() as c:
                r = c.post("/messages", json=payload)
                r.raise_for_status()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e

    def search(self, query: str, limit: int) -> list[dict]:
        try:
            with self._client() as c:
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
            with self._client() as c:
                r = c.get("/healthcheck")
                r.raise_for_status()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e
        return True
