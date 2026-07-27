# Graphiti Shared Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Wizard dual-write every note/session/meeting into a shared Graphiti knowledge graph under a `wizard` namespace and serve `search` from Graphiti when reachable, falling back to the existing SQLite hybrid engine — with no change to any MCP tool or `SearchResult` schema.

**Architecture:** Graphiti is a new **integration** (thin `httpx` REST client, no business logic) wrapped by a new **service** (`GraphMemoryService`) that maps Wizard entities to episodes, enforces the scrub boundary, and orchestrates the Graphiti-primary/SQLite-fallback search branch. Dual-writes ride the existing `spawn_background(...)` fire-and-forget seam so they never block or fail a tool call. Everything is gated behind `settings.graphiti.enabled` (default `False`), making the change inert until opted in.

**Tech Stack:** Python 3.13, FastMCP 3.x, SQLModel/SQLAlchemy, Pydantic v2, Typer CLI, `httpx>=0.27` (already a dependency), pytest + `uv run`.

## Global Constraints

- Run tests only via `uv run pytest` — never `python -m pytest` (system Python lacks the venv deps).
- Every `src/wizard/**/*.py` and `tests/**/*.py` file ≤ 500 lines (pre-commit hook blocks otherwise).
- Unidirectional deps: `tools → services → integrations`, `tools → repositories`. Integrations contain **no** business logic (no mapping/filtering) — CLAUDE.md rule 4.
- No `_` prefix on functions imported by other modules; no `_helpers.py` (use `helpers.py`) — rule 6.
- No N+1: batch-load with `.in_()` + dict lookup — rule 8.
- Scrub PII **before** persistence; episodes are built only from already-scrubbed content.
- Do not change any MCP tool signature or the `SearchResult` / `SearchResponse` schema.
- Default `settings.graphiti.enabled = False` — legacy behavior must be byte-identical when off.
- `group_id = "wizard"`; episode `uuid = f"wizard-{entity_type}-{db_id}"`; `reference_time = created_at`.
- **Assumption pending KiranOS coordination** (spec Open Questions): REST routes `POST /messages` and
  `POST /search`, local embedder, `group_id="wizard"`. `GraphitiClient` isolates these so the exact
  payload can be adjusted in one file once KiranOS pins the contract.

**Spec:** `docs/spec-graphiti-shared-substrate.md`

---

### Task 1: Graphiti config settings

**Files:**
- Modify: `src/wizard/config.py` (add `GraphitiSettings` near `SynthesisSettings` ~line 70; add field to `Settings` ~line 142)
- Test: `tests/test_config.py` (create if absent; else add to existing config test file)

**Interfaces:**
- Produces: `settings.graphiti` → `GraphitiSettings` with `.enabled: bool`, `.url: str`,
  `.group_id: str`, `.timeout_seconds: float`, `.health_ttl_seconds: float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from wizard.config import Settings


def test_graphiti_defaults_are_inert():
    s = Settings()
    assert s.graphiti.enabled is False
    assert s.graphiti.url == "http://localhost:8000"
    assert s.graphiti.group_id == "wizard"
    assert s.graphiti.timeout_seconds == 2.0
    assert s.graphiti.health_ttl_seconds == 30.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_graphiti_defaults_are_inert -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'graphiti'`

- [ ] **Step 3: Write minimal implementation**

```python
# config.py — add after SynthesisSettings
class GraphitiSettings(BaseModel):
    enabled: bool = False
    url: str = "http://localhost:8000"
    group_id: str = "wizard"
    timeout_seconds: float = 2.0
    health_ttl_seconds: float = 30.0
```

```python
# config.py — add to Settings, after `synthesis: SynthesisSettings = ...`
    graphiti: GraphitiSettings = Field(default_factory=GraphitiSettings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_graphiti_defaults_are_inert -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/config.py tests/test_config.py
git commit -m "feat(graphiti): add GraphitiSettings (default disabled)"
```

---

### Task 2: GraphitiClient integration (thin HTTP wrapper)

**Files:**
- Create: `src/wizard/integrations/graphiti.py`
- Create: `src/wizard/integrations/__init__.py` (if `integrations/` doesn't exist yet — check first;
  today integrations may live in a single `integrations.py`. If a module `integrations.py` exists,
  per CLAUDE.md the 3rd-client rule triggers a package split — but for THIS task, create the
  `integrations/graphiti.py` module and, if only `integrations.py` exists, leave it; do not migrate
  existing clients in this task.)
- Modify: `src/wizard/exceptions.py` (add `GraphitiUnavailable`)
- Test: `tests/test_graphiti_client.py`

**Interfaces:**
- Consumes: `GraphitiSettings` (Task 1) — passed in via constructor.
- Produces:
  - `class GraphitiUnavailable(Exception)`
  - `class GraphitiClient` with:
    - `__init__(self, url: str, group_id: str, timeout_seconds: float)`
    - `add_episode(self, name: str, body: str, reference_time: datetime, uuid: str, source_description: str) -> None`
    - `search(self, query: str, limit: int) -> list[str]` — returns episode uuids in rank order
    - `health(self) -> bool`
  - All methods raise `GraphitiUnavailable` on connection/HTTP error (never `httpx` errors directly).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graphiti_client.py
from datetime import datetime

import httpx
import pytest

from wizard.exceptions import GraphitiUnavailable
from wizard.integrations.graphiti import GraphitiClient


def _client(handler) -> GraphitiClient:
    c = GraphitiClient(url="http://graph.test", group_id="wizard", timeout_seconds=1.0)
    c._transport = httpx.MockTransport(handler)  # test seam
    return c


def test_add_episode_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = httpx.Response(200).json if False else __import__("json").loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).add_episode(
        name="note 42", body='{"kind":"note"}',
        reference_time=datetime(2026, 7, 28, 12, 0, 0),
        uuid="wizard-note-42", source_description="wizard:note",
    )
    assert seen["url"] == "http://graph.test/messages"
    assert seen["json"]["group_id"] == "wizard"
    assert seen["json"]["messages"][0]["uuid"] == "wizard-note-42"


def test_search_returns_uuids_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [
            {"uuid": "wizard-note-42"}, {"uuid": "wizard-session-5"}]})

    assert _client(handler).search("db lock", limit=10) == [
        "wizard-note-42", "wizard-session-5"]


def test_connection_error_raises_graphiti_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(GraphitiUnavailable):
        _client(handler).health()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graphiti_client.py -v`
Expected: FAIL — `ModuleNotFoundError: wizard.integrations.graphiti`

- [ ] **Step 3: Write minimal implementation**

```python
# src/wizard/exceptions.py — add
class GraphitiUnavailable(Exception):
    """Raised when the shared Graphiti graph service is unreachable or errors."""
```

```python
# src/wizard/integrations/graphiti.py
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

    def search(self, query: str, limit: int) -> list[str]:
        try:
            with self._client() as c:
                r = c.post("/search", json={
                    "query": query, "group_ids": [self._group_id], "max_facts": limit,
                })
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e
        return [item["uuid"] for item in data.get("results", []) if item.get("uuid")]

    def health(self) -> bool:
        try:
            with self._client() as c:
                r = c.get("/health")
                r.raise_for_status()
        except httpx.HTTPError as e:
            raise GraphitiUnavailable(str(e)) from e
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graphiti_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/integrations/graphiti.py src/wizard/integrations/__init__.py src/wizard/exceptions.py tests/test_graphiti_client.py
git commit -m "feat(graphiti): add thin GraphitiClient REST integration"
```

---

### Task 3: Episode mapping helpers (uuid ↔ entity, body builders)

**Files:**
- Create: `src/wizard/graph_memory.py` (service module — mapping + orchestration live here)
- Test: `tests/test_graph_memory.py`

**Interfaces:**
- Produces (pure functions, no I/O — tested in isolation):
  - `episode_uuid(entity_type: str, entity_id: int) -> str` → `"wizard-{type}-{id}"`
  - `parse_episode_uuid(uuid: str) -> tuple[str, int] | None` → `("note", 42)` or `None` if not ours
  - `note_body(note_type: str, content: str, mental_model: str | None, task_id: int | None, session_id: int | None, supersedes_note_id: int | None) -> str` (JSON string)
  - `session_body(intent, state_delta, open_loops, next_actions, closure_status) -> str`
  - `meeting_body(title: str, category: str, content: str, summary: str | None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_memory.py
import json

from wizard.graph_memory import (
    episode_uuid, parse_episode_uuid, note_body,
)


def test_uuid_round_trip():
    assert episode_uuid("note", 42) == "wizard-note-42"
    assert parse_episode_uuid("wizard-note-42") == ("note", 42)


def test_parse_rejects_foreign_uuids():
    assert parse_episode_uuid("kiranos-idea-9") is None
    assert parse_episode_uuid("garbage") is None
    assert parse_episode_uuid("wizard-note-notanint") is None


def test_note_body_encodes_supersedes_uuid():
    body = json.loads(note_body(
        note_type="DECISION", content="use WAL", mental_model="lock contention",
        task_id=17, session_id=5, supersedes_note_id=39,
    ))
    assert body == {
        "kind": "note", "id": None, "note_type": "DECISION", "content": "use WAL",
        "mental_model": "lock contention", "task_id": 17, "session_id": 5,
        "supersedes": "wizard-note-39",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: wizard.graph_memory`

- [ ] **Step 3: Write minimal implementation**

```python
# src/wizard/graph_memory.py
"""GraphMemoryService — maps Wizard entities to Graphiti episodes and
orchestrates Graphiti-primary / SQLite-fallback search."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_VALID_TYPES = {"note", "session", "meeting", "task"}


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/graph_memory.py tests/test_graph_memory.py
git commit -m "feat(graphiti): add episode mapping helpers with uuid round-trip"
```

---

### Task 4: GraphMemoryService — push_episode + reachability cache

**Files:**
- Modify: `src/wizard/graph_memory.py`
- Modify: `src/wizard/deps.py` (add `get_graphiti_client`, `get_graph_memory_service`)
- Test: `tests/test_graph_memory.py`

**Interfaces:**
- Consumes: `GraphitiClient` (Task 2), body builders + `episode_uuid` (Task 3), `GraphitiSettings` (Task 1).
- Produces:
  - `class GraphMemoryService(__init__(self, client: GraphitiClient, enabled: bool))`
    - `push_episode(self, entity_type: str, entity_id: int, body: str, name: str, reference_time: datetime) -> None`
      — no-op when `enabled` is False; swallows `GraphitiUnavailable`.
    - `is_reachable(self) -> bool` — TTL-cached `client.health()`; False on `GraphitiUnavailable`.
  - `deps.get_graphiti_client() -> GraphitiClient`, `deps.get_graph_memory_service() -> GraphMemoryService`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_memory.py — append
from datetime import datetime
from unittest.mock import MagicMock

from wizard.exceptions import GraphitiUnavailable
from wizard.graph_memory import GraphMemoryService


def test_push_episode_noop_when_disabled():
    client = MagicMock()
    GraphMemoryService(client=client, enabled=False).push_episode(
        "note", 42, '{"kind":"note"}', "note 42", datetime(2026, 7, 28))
    client.add_episode.assert_not_called()


def test_push_episode_swallows_unavailable():
    client = MagicMock()
    client.add_episode.side_effect = GraphitiUnavailable("down")
    # must not raise
    GraphMemoryService(client=client, enabled=True).push_episode(
        "note", 42, '{"kind":"note"}', "note 42", datetime(2026, 7, 28))
    client.add_episode.assert_called_once()


def test_is_reachable_false_on_unavailable():
    client = MagicMock()
    client.health.side_effect = GraphitiUnavailable("down")
    assert GraphMemoryService(client=client, enabled=True).is_reachable() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_memory.py -k "push_episode or is_reachable" -v`
Expected: FAIL — `ImportError: cannot import name 'GraphMemoryService'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/wizard/graph_memory.py — add imports at top
import time
from datetime import datetime

from .exceptions import GraphitiUnavailable
from .integrations.graphiti import GraphitiClient
```

```python
# src/wizard/graph_memory.py — append class
class GraphMemoryService:
    def __init__(self, client: GraphitiClient, enabled: bool, health_ttl_seconds: float = 30.0) -> None:
        self._client = client
        self._enabled = enabled
        self._ttl = health_ttl_seconds
        self._reachable_cache: tuple[float, bool] | None = None

    def push_episode(
        self, entity_type: str, entity_id: int, body: str,
        name: str, reference_time: datetime,
    ) -> None:
        if not self._enabled:
            return
        try:
            self._client.add_episode(
                name=name, body=body, reference_time=reference_time,
                uuid=episode_uuid(entity_type, entity_id),
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
```

```python
# src/wizard/deps.py — add import
from .graph_memory import GraphMemoryService
from .integrations.graphiti import GraphitiClient
```

```python
# src/wizard/deps.py — add factories
def get_graphiti_client() -> GraphitiClient:
    g = settings.graphiti
    return GraphitiClient(url=g.url, group_id=g.group_id, timeout_seconds=g.timeout_seconds)


def get_graph_memory_service() -> GraphMemoryService:
    return GraphMemoryService(
        client=get_graphiti_client(),
        enabled=settings.graphiti.enabled,
        health_ttl_seconds=settings.graphiti.health_ttl_seconds,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_memory.py -v`
Expected: PASS (all Task 3 + Task 4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/wizard/graph_memory.py src/wizard/deps.py tests/test_graph_memory.py
git commit -m "feat(graphiti): add GraphMemoryService push_episode + reachability cache"
```

---

### Task 5: GraphMemoryService.search — Graphiti-primary, SQLite fallback

**Files:**
- Modify: `src/wizard/graph_memory.py`
- Test: `tests/test_graph_memory.py`

**Interfaces:**
- Consumes: `SearchRepository.hybrid_search` (existing, `repositories/search.py:58`), `parse_episode_uuid`,
  `is_reachable`, `GraphitiClient.search`.
- Produces:
  - `GraphMemoryService.search(self, db, query: str, limit: int, entity_type: str | None, search_repo, fetch_display) -> list[SearchResult]`
    - `fetch_display: Callable[[Session, list[tuple[str, int]]], list[SearchResult]]` — batch-fetches
      display fields from SQLite for parsed `(type, id)` pairs (injected so the service stays free of SQL).
    - When `is_reachable()`: call `client.search`, `parse_episode_uuid` each hit (drop foreign/unparseable),
      filter to `entity_type` if given, `fetch_display` for the survivors, preserve Graphiti rank order.
    - Else, or on `GraphitiUnavailable` mid-search: return `search_repo.hybrid_search(db, query, limit, entity_type)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_memory.py — append
from wizard.schemas import SearchResult


def _sr(eid: int) -> SearchResult:
    return SearchResult(entity_type="note", entity_id=eid, title="t", snippet="s")


def test_search_uses_graphiti_when_reachable():
    client = MagicMock()
    client.health.return_value = True
    client.search.return_value = ["wizard-note-42", "kiranos-idea-9", "wizard-note-7"]
    svc = GraphMemoryService(client=client, enabled=True)

    captured = {}
    def fetch_display(db, pairs):
        captured["pairs"] = pairs
        return [_sr(42), _sr(7)]
    repo = MagicMock()

    out = svc.search(db=None, query="q", limit=10, entity_type=None,
                     search_repo=repo, fetch_display=fetch_display)
    # foreign uuid dropped; order preserved
    assert captured["pairs"] == [("note", 42), ("note", 7)]
    assert [r.entity_id for r in out] == [42, 7]
    repo.hybrid_search.assert_not_called()


def test_search_falls_back_when_unreachable():
    client = MagicMock()
    client.health.side_effect = GraphitiUnavailable("down")
    repo = MagicMock()
    repo.hybrid_search.return_value = [_sr(1)]
    svc = GraphMemoryService(client=client, enabled=True)

    out = svc.search(db=None, query="q", limit=10, entity_type=None,
                     search_repo=repo, fetch_display=lambda db, p: [])
    assert [r.entity_id for r in out] == [1]
    repo.hybrid_search.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_memory.py -k "search_uses or search_falls" -v`
Expected: FAIL — `AttributeError: 'GraphMemoryService' object has no attribute 'search'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/wizard/graph_memory.py — add to imports
from collections.abc import Callable

from .schemas import SearchResult
```

```python
# src/wizard/graph_memory.py — add method to GraphMemoryService
    def search(
        self, db, query: str, limit: int, entity_type: str | None,
        search_repo, fetch_display: Callable[[object, list[tuple[str, int]]], list["SearchResult"]],
    ) -> list["SearchResult"]:
        if self.is_reachable():
            try:
                uuids = self._client.search(query, limit)
            except GraphitiUnavailable as e:
                logger.warning("Graphiti search failed, falling back to SQLite: %s", e)
                return search_repo.hybrid_search(db, query, limit=limit, entity_type=entity_type)
            pairs: list[tuple[str, int]] = []
            for u in uuids:
                parsed = parse_episode_uuid(u)
                if parsed is None:
                    continue
                if entity_type is not None and parsed[0] != entity_type:
                    continue
                pairs.append(parsed)
            return fetch_display(db, pairs)[:limit]
        return search_repo.hybrid_search(db, query, limit=limit, entity_type=entity_type)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/graph_memory.py tests/test_graph_memory.py
git commit -m "feat(graphiti): Graphiti-primary search with SQLite fallback"
```

---

### Task 6: SQLite display-fetch for Graphiti hits (SearchRepository method)

**Files:**
- Modify: `src/wizard/repositories/search.py` (add `fetch_by_keys`; keep file ≤ 500 lines — currently 237)
- Test: `tests/test_search_repo.py` (append; create if absent)

**Interfaces:**
- Produces: `SearchRepository.fetch_by_keys(self, db, pairs: list[tuple[str, int]]) -> list[SearchResult]`
  — batch-fetches display fields per entity type using `.in_()` (no N+1), returns in the SAME order as
  `pairs`, dropping any id whose row is missing or (for notes) not `status='active'`. Reuses the exact
  `SearchResult` construction already in `_search_notes/_search_sessions/_search_meetings/_search_tasks`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_repo.py
from wizard.repositories.search import SearchRepository


def test_fetch_by_keys_preserves_order_and_drops_missing(seeded_db):
    # seeded_db fixture: note id=42 active, note id=99 does NOT exist
    repo = SearchRepository()
    out = repo.fetch_by_keys(seeded_db, [("note", 42), ("note", 99)])
    assert [(r.entity_type, r.entity_id) for r in out] == [("note", 42)]
```

Note: reuse the existing test DB fixture in `tests/` (grep `def seeded_db` / `conftest`).
If none seeds a note, add a minimal fixture that inserts one active note id=42 via `NoteRepository`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_search_repo.py::test_fetch_by_keys_preserves_order_and_drops_missing -v`
Expected: FAIL — `AttributeError: 'SearchRepository' object has no attribute 'fetch_by_keys'`

- [ ] **Step 3: Write minimal implementation**

```python
# repositories/search.py — add method to SearchRepository
    def fetch_by_keys(
        self, db: Session, pairs: list[tuple[str, int]]
    ) -> list[SearchResult]:
        """Batch-fetch display fields for (entity_type, id) pairs, preserving
        pair order and dropping rows that are missing/inactive."""
        by_type: dict[str, list[int]] = {}
        for etype, eid in pairs:
            by_type.setdefault(etype, []).append(eid)

        found: dict[Key, SearchResult] = {}
        if by_type.get("note"):
            rows = db.execute(  # type: ignore[call-overload]
                text(
                    "SELECT id AS entity_id, content, note_type, task_id, created_at "
                    "FROM note WHERE id IN :ids AND status = 'active'"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": by_type["note"]},
            ).mappings().fetchall()
            for m in rows:
                found[("note", m["entity_id"])] = SearchResult(
                    entity_type="note", entity_id=m["entity_id"],
                    title=m.get("note_type") or "note",
                    snippet=(m.get("content") or "")[:200],
                    created_at=m.get("created_at"), task_id=m.get("task_id"),
                )
        # session / meeting / task lanes: mirror the SELECTs in _search_sessions /
        # _search_meetings / _search_tasks (same columns, same SearchResult shape),
        # each guarded by `if by_type.get(<type>):`.
        return [found[(t, i)] for (t, i) in pairs if (t, i) in found]
```

Implementer note: fill in the session/meeting/task branches by lifting the SELECT + `SearchResult`
construction verbatim from `_search_sessions` (`search.py:162`), `_search_meetings` (`:190`), and
`_search_tasks` (`:214`) — same columns, batched with `IN :ids`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_search_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/repositories/search.py tests/test_search_repo.py
git commit -m "feat(graphiti): add SearchRepository.fetch_by_keys for graph-hit display"
```

---

### Task 7: Wire `search` tool to GraphMemoryService

**Files:**
- Modify: `src/wizard/tools/query_tools.py:250-265` (the `search` tool)
- Test: `tests/test_query_tools.py` (append) or existing search-tool test

**Interfaces:**
- Consumes: `get_graph_memory_service` (Task 4), `get_search_repo`, `SearchRepository.fetch_by_keys` (Task 6),
  `GraphMemoryService.search` (Task 5).
- Produces: `search` tool with UNCHANGED signature and `SearchResponse` return; behavior now routes through
  the service. When `graphiti.enabled=False`, `is_reachable()` returns False → identical to today.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_query_tools.py — append
import pytest

from wizard.schemas import SearchResponse


@pytest.mark.asyncio
async def test_search_still_returns_searchresponse_when_graphiti_disabled(seeded_db, monkeypatch):
    # graphiti disabled by default → must behave exactly like legacy hybrid_search
    from wizard.tools.query_tools import search
    from wizard.deps import get_graph_memory_service, get_search_repo
    resp = await search(
        query="lock", limit=5, entity_type=None,
        gms=get_graph_memory_service(), s_repo=get_search_repo(), db=seeded_db,
    )
    assert isinstance(resp, SearchResponse)
```

Note: match the actual param-injection style of the existing `search` test. If the current test calls
`search` through the FastMCP tool harness, follow that pattern instead of direct kwargs.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_query_tools.py -k graphiti_disabled -v`
Expected: FAIL — `TypeError: search() got an unexpected keyword argument 'gms'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/query_tools.py — update imports
from ..deps import get_graph_memory_service  # add alongside get_search_repo
from ..graph_memory import GraphMemoryService
```

```python
# tools/query_tools.py — replace the search body
async def search(
    query: str,
    limit: int = 10,
    entity_type: Literal["note", "session", "meeting", "task"] | None = None,
    gms: GraphMemoryService = Depends(get_graph_memory_service),
    s_repo: SearchRepository = Depends(get_search_repo),
    db: Session = Depends(_get_db_session),
) -> SearchResponse:
    """Search across notes, sessions, meetings, and tasks by keyword.

    Serves from the shared Graphiti graph when reachable, else the local
    hybrid BM25+cosine engine. Result shape is identical either way.
    entity_type: optional filter — 'note', 'session', 'meeting', or 'task'.
    """
    if not query.strip():
        raise ToolError("query must not be empty")
    results = gms.search(
        db=db, query=query, limit=limit, entity_type=entity_type,
        search_repo=s_repo, fetch_display=s_repo.fetch_by_keys,
    )
    return SearchResponse(results=results, total=len(results))
```

- [ ] **Step 4: Run the full search-related suite**

Run: `uv run pytest tests/test_query_tools.py tests/test_graph_memory.py -v`
Expected: PASS — existing search tests still green (disabled path == legacy).

- [ ] **Step 5: Commit**

```bash
git add src/wizard/tools/query_tools.py tests/test_query_tools.py
git commit -m "feat(graphiti): route search tool through GraphMemoryService"
```

---

### Task 8: Dual-write on save_note

**Files:**
- Modify: `src/wizard/tools/task_tools.py` (`save_note` ~line 292; inject `gms`, spawn push next to `write_embedding` at `:348`)
- Test: `tests/test_task_tools.py` (append)

**Interfaces:**
- Consumes: `get_graph_memory_service` (Task 4), `note_body` + `episode_uuid` (Task 3).
- Produces: `save_note` unchanged signature except an added `gms: GraphMemoryService = Depends(get_graph_memory_service)`
  injected param (agents never pass it). After a non-duplicate persist, spawns `gms.push_episode(...)` in the background.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_task_tools.py — append
import pytest


@pytest.mark.asyncio
async def test_save_note_dual_writes_episode_when_enabled(monkeypatch, ...fixtures):
    from unittest.mock import MagicMock
    gms = MagicMock()
    # ...call save_note through the existing test harness with gms injected,
    # note_type=DECISION, content="use WAL", on a task with a prior note so it's not a dup
    # assert gms.push_episode called once with entity_type="note" and a body containing "DECISION"
    args = gms.push_episode.call_args
    assert args.kwargs["entity_type"] == "note"
    assert '"note_type": "DECISION"' in args.kwargs["body"]
```

Note: model this on the existing `save_note` test (grep `def test_save_note` in `tests/`). Reuse its
task/session setup fixtures. `spawn_background` runs the coroutine on the loop — if the existing tests
await settling, follow that; otherwise assert on a synchronous `push_episode` call by having the test
inject a `gms` whose `push_episode` is a plain MagicMock (spawn wraps a sync call in a coroutine —
see Step 3; keep `push_episode` synchronous so the assertion is deterministic).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_task_tools.py -k dual_writes -v`
Expected: FAIL — `save_note` has no `gms` param / `push_episode` not called.

- [ ] **Step 3: Write minimal implementation**

```python
# tools/task_tools.py — add imports
from ..deps import get_graph_memory_service  # alongside existing deps
from ..graph_memory import GraphMemoryService, episode_uuid, note_body
```

```python
# tools/task_tools.py — add injected param to save_note signature
    gms: GraphMemoryService = Depends(get_graph_memory_service),
```

```python
# tools/task_tools.py — inside save_note, replace the existing:
#     if not result.was_duplicate:
#         spawn_background(write_embedding(result.note_id, clean))
# with:
        if not result.was_duplicate:
            spawn_background(write_embedding(result.note_id, clean))

            async def _push() -> None:
                gms.push_episode(
                    entity_type="note", entity_id=result.note_id,
                    name=f"note {result.note_id}",
                    reference_time=datetime.now(),
                    body=note_body(
                        note_type=note_type.value, content=clean,
                        mental_model=mental_model, task_id=task_db_id,
                        session_id=session_id, supersedes_note_id=None,
                    ),
                )

            spawn_background(_push())
```

Note: import `datetime` if not already present (`from datetime import datetime`). `push_episode` is
sync and internally guarded by `enabled`; wrapping in an async thunk keeps it on the `spawn_background`
seam without blocking. If `spawn_background` requires a truly non-blocking body, wrap the call with
`asyncio.to_thread(gms.push_episode, ...)` — mirror how `write_embedding` uses `asyncio.to_thread`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_task_tools.py -k dual_writes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/tools/task_tools.py tests/test_task_tools.py
git commit -m "feat(graphiti): dual-write note episodes on save_note"
```

---

### Task 9: Dual-write on session_end and ingest_meeting

**Files:**
- Modify: `src/wizard/tools/session_tools.py` (after `_persist_session_end`, `session_end` ~line 320)
- Modify: `src/wizard/tools/meeting_tools.py` (after `ingest_meeting` ~line 187 and/or `save_meeting_summary` ~line 108)
- Test: `tests/test_session_tools.py`, `tests/test_meeting_tools.py` (append)

**Interfaces:**
- Consumes: `get_graph_memory_service`, `session_body`, `meeting_body`, `episode_uuid` (Task 3/4).
- Produces: `session_end` and `ingest_meeting`/`save_meeting_summary` each gain an injected `gms` param
  and spawn `gms.push_episode(entity_type="session"|"meeting", ...)` after their persist step.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_tools.py — append
@pytest.mark.asyncio
async def test_session_end_dual_writes_session_episode(...fixtures):
    from unittest.mock import MagicMock
    gms = MagicMock()
    # call session_end through the existing harness with gms injected + a valid SessionState
    args = gms.push_episode.call_args
    assert args.kwargs["entity_type"] == "session"
    assert '"kind": "session"' in args.kwargs["body"]
```

```python
# tests/test_meeting_tools.py — append
@pytest.mark.asyncio
async def test_ingest_meeting_dual_writes_meeting_episode(...fixtures):
    from unittest.mock import MagicMock
    gms = MagicMock()
    args = gms.push_episode.call_args
    assert args.kwargs["entity_type"] == "meeting"
```

Note: mirror the existing `session_end` / `ingest_meeting` tests for setup. Use the scrubbed
`content`/`summary` that those tools already produce as the episode body inputs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_session_tools.py tests/test_meeting_tools.py -k dual_writes -v`
Expected: FAIL — `gms` param missing / `push_episode` not called.

- [ ] **Step 3: Write minimal implementation**

For `session_end` (after the persist that yields the session id + resolved `SessionState` fields):

```python
# session_tools.py — imports
from ..deps import get_graph_memory_service
from ..graph_memory import GraphMemoryService, session_body
```

```python
# session_tools.py — inject param
    gms: GraphMemoryService = Depends(get_graph_memory_service),
```

```python
# session_tools.py — after response is built (session id known), spawn:
    async def _push_session() -> None:
        gms.push_episode(
            entity_type="session", entity_id=response.session_id,
            name=f"session {response.session_id}",
            reference_time=datetime.now(),
            body=session_body(
                intent=response.intent or "", state_delta=state.state_delta,
                open_loops=state.open_loops, next_actions=state.next_actions,
                closure_status=state.closure_status,
            ),
        )
    spawn_background(_push_session())
```

(Adapt field access to the actual `SessionState`/response objects in scope — the SessionState instance
built in `_persist_session_end`. If `state` isn't in `session_end`'s scope, thread the needed values out
of `_persist_session_end`'s return or read them from `response`.)

For `ingest_meeting` (and `save_meeting_summary` if that's where summary is finalized) — same pattern with
`meeting_body(title, category, content, summary)` and `entity_type="meeting"`, using the meeting id + the
already-scrubbed content the tool persisted.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session_tools.py tests/test_meeting_tools.py -k dual_writes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/tools/session_tools.py src/wizard/tools/meeting_tools.py tests/test_session_tools.py tests/test_meeting_tools.py
git commit -m "feat(graphiti): dual-write session and meeting episodes"
```

---

### Task 10: `wizard backfill-graphiti` CLI command

**Files:**
- Create: `src/wizard/cli/graphiti.py`
- Modify: `src/wizard/cli/main.py` (register command near the existing `backfill-embeddings` at `:431`)
- Test: `tests/test_cli_graphiti.py`

**Interfaces:**
- Consumes: `GraphitiClient`, `episode_uuid` + body builders (Task 3), `settings.graphiti`, `SecurityService`.
- Produces: `wizard backfill-graphiti` — streams all SQLite notes/sessions/meetings into the graph with
  deterministic uuids (idempotent via uuid; safe to re-run), scrubbing legacy content defensively before push.
  Exits with a clear message if `graphiti.enabled` is False or the service is unreachable.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_graphiti.py
from unittest.mock import MagicMock

from wizard.cli.graphiti import run_backfill_graphiti


def test_backfill_pushes_one_episode_per_note(seeded_db, monkeypatch):
    client = MagicMock()
    # monkeypatch the client factory + settings.graphiti.enabled=True + db path to seeded_db
    # seeded_db has exactly 1 active note (id=42)
    run_backfill_graphiti(client=client, enabled=True, db=seeded_db, security=_noop_scrubber())
    uuids = [c.kwargs["uuid"] for c in client.add_episode.call_args_list]
    assert "wizard-note-42" in uuids


def test_backfill_noop_when_disabled(capsys):
    run_backfill_graphiti(client=MagicMock(), enabled=False, db=None, security=None)
    assert "disabled" in capsys.readouterr().out.lower()
```

Note: design `run_backfill_graphiti` to take its dependencies as parameters (client, enabled, db,
security) so it's unit-testable without a live service — the Typer command wires the real ones.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_graphiti.py -v`
Expected: FAIL — `ModuleNotFoundError: wizard.cli.graphiti`

- [ ] **Step 3: Write minimal implementation**

```python
# src/wizard/cli/graphiti.py
"""Backfill existing SQLite notes/sessions/meetings into the shared Graphiti graph."""

from __future__ import annotations

import logging
from datetime import datetime

import typer

from wizard.config import settings
from wizard.graph_memory import meeting_body, note_body, session_body

logger = logging.getLogger(__name__)


def run_backfill_graphiti(client, enabled: bool, db, security) -> None:
    if not enabled:
        typer.echo("Graphiti is disabled (settings.graphiti.enabled=false). Nothing to do.")
        return
    # NOTES
    note_rows = db.execute(  # SQL: id, note_type, content, mental_model, task_id, session_id, created_at
        __import__("sqlalchemy").text(
            "SELECT id, note_type, content, mental_model, task_id, session_id, created_at "
            "FROM note WHERE status = 'active'"
        )
    ).mappings().fetchall()
    pushed = 0
    for r in note_rows:
        content = security.scrub(r["content"]).clean if security else r["content"]
        client.add_episode(
            name=f"note {r['id']}",
            body=note_body(
                note_type=r["note_type"], content=content, mental_model=r["mental_model"],
                task_id=r["task_id"], session_id=r["session_id"], supersedes_note_id=None,
            ),
            reference_time=_ts(r["created_at"]),
            uuid=f"wizard-note-{r['id']}", source_description="wizard:note",
        )
        pushed += 1
    # SESSIONS + MEETINGS: same shape, using session_body / meeting_body and their uuids.
    typer.echo(f"Backfill complete. Pushed {pushed} note episode(s) (+ sessions, meetings).")


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
```

```python
# src/wizard/cli/main.py — register (near backfill-embeddings at :431)
@app.command("backfill-graphiti")
def backfill_graphiti() -> None:
    """Push existing notes/sessions/meetings into the shared Graphiti graph."""
    from wizard.cli.graphiti import run_backfill_graphiti
    from wizard.database import get_session
    from wizard.deps import get_graphiti_client, get_security
    with get_session() as db:
        run_backfill_graphiti(
            client=get_graphiti_client(),
            enabled=settings.graphiti.enabled,
            db=db, security=get_security(),
        )
```

Implementer note: fill in the session/meeting loops mirroring the note loop — `SELECT` the fields each
body builder needs, scrub `content`/`summary`, use `wizard-session-{id}` / `wizard-meeting-{id}` uuids.
Idempotency comes for free from Graphiti's `uuid` upsert; re-running pushes the same uuids.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_graphiti.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/wizard/cli/graphiti.py src/wizard/cli/main.py tests/test_cli_graphiti.py
git commit -m "feat(graphiti): add wizard backfill-graphiti CLI command"
```

---

### Task 11: Full-suite regression + docs

**Files:**
- Modify: `CLAUDE.md` (add `wizard backfill-graphiti` to "Running the Server" list; note Graphiti substrate)
- Modify: `docs/dev/architecture.md` (add Graphiti integration/service to the layer map) — if present
- No new test file; this task is the green-suite gate.

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS — all pre-existing tests green (proves the substrate swap is behavior-preserving when
`graphiti.enabled=False`), plus all new tests from Tasks 1–10.

- [ ] **Step 2: Run ruff + line-count pre-commit checks**

Run: `uv run ruff check src/wizard tests && bash scripts/pre-commit`
Expected: PASS — no file over 500 lines, no cross-layer import (verify `graph_memory.py` imports the
integration, and `integrations/graphiti.py` imports nothing from `tools`/`repositories`/`services`).

- [ ] **Step 3: Update docs**

Add to `CLAUDE.md` under "Running the Server":
```
wizard backfill-graphiti   # push existing notes/sessions/meetings into the shared Graphiti graph
```
Add a one-line note under "Key Invariants": search serves from Graphiti when
`settings.graphiti.enabled` and the service is reachable; otherwise the local hybrid engine.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/dev/architecture.md
git commit -m "docs(graphiti): document shared substrate + backfill command"
```

---

## Self-Review

**Spec coverage:**
- Integration shape (dual-write + fallback) → Tasks 4, 5, 7, 8, 9 ✓
- REST graph-service contract, local embedder → Task 2 (isolated client) ✓
- Search Graphiti-primary / SQLite-fallback → Tasks 5, 7 ✓
- Episode mapping (one per note/session/meeting, JSON body) → Tasks 3, 8, 9 ✓
- Result mapping (uuid parse → SQLite display) → Tasks 3, 5, 6 ✓
- Preserve MCP surface + `SearchResult` schema → Tasks 7 (unchanged signature/schema), 11 (regression) ✓
- Graceful degradation (never hard-fail) → Task 4 (swallow + no-op when disabled), Task 5 (fallback) ✓
- PII scrubbing before graph → Tasks 8/9 (scrubbed `clean`), Task 10 (defensive re-scrub) ✓
- Backfill command → Task 10 ✓
- `enabled=False` inert default → Task 1, verified in Tasks 7 & 11 ✓
- Open questions / contract isolation → Global Constraints + Task 2 ✓

**Placeholder scan:** Task steps carry real code. Where a step lifts existing SELECTs verbatim
(Tasks 6, 9, 10 session/meeting branches), the exact source line references are given rather than
re-pasting, to avoid drift from the real code — implementer copies from the cited lines.

**Type consistency:** `push_episode(entity_type, entity_id, body, name, reference_time)`,
`episode_uuid(entity_type, entity_id)`, `parse_episode_uuid → tuple[str,int]|None`,
`fetch_by_keys(db, pairs) -> list[SearchResult]`, `GraphMemoryService.search(...)` signature — all
consistent across Tasks 3–10. `SearchResult` shape untouched throughout.

## Open Questions (carried from spec — resolve with KiranOS before/at Task 2)

1. Local embedder on the graph service (no `OPENAI_API_KEY`)?
2. Exact REST routes + payload for add/search (Task 2's client is the single adjustment point).
3. `group_id` literals (`wizard` / `kiranos`) + unified cross-source recall.
4. uuid namespace (`wizard-{type}-{id}`) collision-free with KiranOS.
5. `graphiti-core` / `zepai/graphiti` version pin.
