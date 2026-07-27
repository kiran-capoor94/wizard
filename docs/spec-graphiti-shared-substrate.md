# Design: Migrate Wizard's memory substrate to a shared Graphiti knowledge graph

**Date:** 2026-07-28
**Branch:** `feat/graphiti-shared-substrate`
**Status:** Approved design — pending implementation plan

## Problem

Wizard (Python 3.13 / FastMCP 3.x / SQLite persistent-memory MCP server, v2.2.42)
does retrieval with its own hybrid engine: SQLite FTS5 (BM25, Porter stemming) fused
by Reciprocal Rank Fusion with a semantic lane (`sentence-transformers all-MiniLM-L6-v2`,
384-dim, `sqlite-vec` cosine over NOTES only). See `repositories/search.py` and
`embedding.py`.

Wizard is being federated into KiranOS (a control plane) whose "Brain" uses **Graphiti**
— a temporal knowledge graph (facts with validity windows, provenance, hybrid
semantic+keyword+graph retrieval). Running Wizard's bespoke MiniLM+sqlite-vec+FTS engine
alongside Graphiti means two memory algorithms over what should be one brain.

**Goal:** one shared substrate. Wizard's agent/session memory writes into and reads from
the SAME Graphiti graph KiranOS uses, under a `wizard` source namespace, so there is a
single retrieval algorithm and a unified, temporal, provenance-aware graph across both
systems — **without** changing Wizard's MCP tool contract or behavior.

## Chosen approach — Dual-write + Graphiti-backed search with SQLite fallback (option b)

SQLite remains the source-of-truth for all operational/relational data and for display.
After a note/session/meeting is scrubbed and persisted, Wizard **dual-writes** an episode
to the shared Graphiti graph under `group_id="wizard"`. The `search` tool queries Graphiti
when it is reachable and **transparently falls back** to the existing `hybrid_search` when
it is not. `SearchResponse`/`SearchResult` stays byte-identical.

Rejected alternatives:
- **(a) Graphiti as primary store** — couples every `session_start` to a live Docker
  service and discards a tested, zero-dependency retrieval engine. Deferred as the eventual
  target once (b) is proven in production.
- **(c) Mirror only** — dual-write but leave `search` on SQLite. Doesn't deliver the brief's
  "Graphiti-backed search" deliverable.

**Why (b) fits this codebase specifically:** `save_note` already fires `write_embedding()`
as a fire-and-forget background task that swallows its own errors (`task_tools.py:271`,
spawned at `:348`). A Graphiti dual-write placed at the same seam inherits the exact
"never block a tool call, never hard-fail" semantics for free. And the existing sqlite-vec
engine becomes the fallback rather than dead code — the graceful-degradation path the brief
requires already exists as tested code.

## Confirmed facts (verified against source + current Graphiti docs)

Wizard side:
- `save_note` (`task_tools.py:292`) → scrub (`SecurityService.scrub`, returns `ScrubResult.clean`)
  → `_persist_note` (`:206`) → `spawn_background(write_embedding(...))` (`:348`). Scrubbing
  happens **before** persistence, so any Graphiti write after `_persist_note` inherits clean content.
- `embedding.embed()` returns `None` (never raises) when the model is unavailable → BM25-only
  fallback. This is the template for Graphiti degradation.
- 21 MCP tools registered. `SearchResult` = `{entity_type: Literal["note","session","meeting","task"],
  entity_id: int, title, snippet, created_at, task_id}`.
- `deps.py` wires repositories as plain factory functions (`get_search_repo()` → `SearchRepository()`).

Graphiti side:
- `group_id` is Graphiti's native namespacing primitive: `add_episode(..., group_id=...)` and
  `search(..., group_ids=[...])`. This IS the `wizard`/`kiranos` partition — no custom tagging.
- `add_episode(name, episode_body, source_description, reference_time, source=EpisodeType.json,
  group_id, uuid, ...)` accepts structured JSON, an explicit `reference_time`, and an idempotent
  `uuid` (safe re-backfill).
- Wizard talks to the **REST graph service** (`zepai/graphiti`, `:8000`), not the MCP server.
- **KiranOS configures the graph service with a LOCAL LLM/embedder** (no `OPENAI_API_KEY`) to
  honor local-first. This is a KiranOS docker-compose responsibility (see Open Questions).

## Contract decisions (settled)

| Decision | Choice |
| --- | --- |
| HTTP surface | REST graph service (`GRAPHITI_URL`, default `http://localhost:8000`), local embedder |
| Search when Graphiti up | Graphiti **only**; SQLite `hybrid_search` is fallback when unreachable/errors |
| Entity → episode | One episode per note / session-close / meeting; rich fields as JSON body |
| Result mapping | Episode-level: parse `uuid` → `(entity_type, int id)`, fetch title/snippet from SQLite |

## Architecture

Dependencies stay unidirectional (`tools → services → integrations`, `tools → repositories`).
Graphiti is an **integration** (thin HTTP client, no business logic) wrapped by a **service**
(mapping, scrubbing-boundary enforcement, fallback orchestration).

```
save_note / session_end / ingest_meeting (tools)
        │  (after scrub + _persist_note)
        ▼
  GraphMemoryService.push_episode(entity_type, id, payload)   [services]
        │  builds episode body + deterministic uuid + reference_time
        ▼
  GraphitiClient.add_episode(...)   [integrations]  ── HTTP ──▶ graph service :8000

search (tool)
        ▼
  GraphMemoryService.search(query, limit, entity_type)   [services]
        │  reachable? ── yes ─▶ GraphitiClient.search(group_ids=["wizard"])
        │                          │ parse uuids → (type,id) → SQLite fetch → SearchResult
        │  reachable? ── no  ─▶ SearchRepository.hybrid_search(...)   [existing, unchanged]
        ▼
  SearchResponse   (schema unchanged)
```

### Components

1. **`integrations/graphiti.py` — `GraphitiClient`** (thin HTTP wrapper).
   - `add_episode(group_id, name, body, reference_time, uuid, source_description)`,
     `search(query, group_ids, limit)`, `health()`.
   - Uses `httpx` with a short connect timeout. Raises typed `GraphitiUnavailable` on any
     connection/HTTP error. **No mapping, no business logic** (CLAUDE.md rule 4).
   - Reachability is cached with a short TTL so `search` doesn't pay a probe per call.

2. **`services.py` — `GraphMemoryService`** (or a new `graph_memory.py` if `services.py`
   nears the 500-line cap — checked during implementation).
   - `push_episode(entity_type, entity_id, payload, reference_time)` — builds the JSON body,
     computes `uuid = f"wizard-{entity_type}-{entity_id}"`, calls the client. Swallows/logs
     `GraphitiUnavailable` (dual-write must never fail the originating tool).
   - `search(query, limit, entity_type)` — reachability branch above; maps Graphiti episode
     results back to `SearchResult` by parsing the uuid and fetching display fields from SQLite;
     falls back to `SearchRepository.hybrid_search` otherwise.

3. **`config.py` — `GraphitiSettings`**: `enabled: bool = False`, `url: str = "http://localhost:8000"`,
   `group_id: str = "wizard"`, `timeout_seconds: float`, reachability-cache TTL. Overridable by
   `GRAPHITI_URL` env (matches existing `WIZARD_DB` env pattern). **Default `enabled=False`** so
   the change is inert until KiranOS's service exists and the user opts in.

4. **`deps.py`**: `get_graphiti_client()`, `get_graph_memory_service()` — plain factory functions
   matching `get_search_repo()`.

5. **`cli/main.py` + new `cli/graphiti.py`**: `wizard backfill-graphiti` — mirrors
   `cli/embeddings.py`; streams existing SQLite notes/sessions/meetings into the graph with
   deterministic uuids (idempotent; re-runnable). Scrubs on the way if any legacy rows predate
   scrubbing (defensive; scrub is idempotent).

## Episode schema (the shared contract)

`group_id = "wizard"`; `uuid = "wizard-{entity_type}-{db_id}"`; `reference_time = created_at`;
`source = EpisodeType.json`; `source_description = "wizard:{entity_type}"`.

```jsonc
// note 42
{ "kind": "note", "id": 42, "note_type": "DECISION", "content": "<scrubbed>",
  "mental_model": "<scrubbed|null>", "task_id": 17, "session_id": 5,
  "supersedes": "wizard-note-39" }        // null when no supersedes_note_id

// session-close 5
{ "kind": "session", "id": 5, "intent": "...", "state_delta": "...",
  "open_loops": ["..."], "next_actions": ["..."], "closure_status": "clean" }

// meeting 8
{ "kind": "meeting", "id": 8, "title": "...", "category": "planning",
  "content": "<scrubbed>", "summary": "<scrubbed|null>" }
```

Graphiti extracts entities and temporal edges from these bodies; the JSON keys preserve
Wizard's rich types (NoteType, `mental_model`, `supersedes` → a temporal supersession edge,
`state_delta`/`open_loops`) as first-class graph properties with validity windows.

## Data flow — search result mapping

Graphiti (graphiti mode) returns episode hits → for each, parse `uuid` → `(entity_type, id)` →
batch-fetch display fields from SQLite (`.in_()`, no N+1 — CLAUDE.md rule 8) → build
`SearchResult` exactly as the SQLite lanes do today. A Graphiti hit whose SQLite row is gone
(deleted/superseded to non-active) is dropped, matching current `status='active'` filtering.

## Error handling & graceful degradation

- **Dual-write**: `push_episode` runs via `spawn_background(...)`, the same fire-and-forget helper
  `save_note` already uses for `write_embedding` (`task_tools.py:348`). `save_note` gets the call
  added next to the existing embedding spawn; `session_end` and `ingest_meeting` each get their own
  `spawn_background(push_episode(...))` after their persist step (they have no such seam today).
  `GraphitiUnavailable` is logged at WARNING and swallowed — the row is already durably in SQLite.
- **Search**: reachability probe (cached) decides the branch. Any error mid-Graphiti-search →
  fall back to `hybrid_search` for that call and log once. `session_start` never touches Graphiti
  on its hot path, so a down graph never blocks session creation.
- **`enabled=False`**: every Graphiti path is a no-op; behavior is byte-identical to v2.2.42.

## PII scrubbing

Unchanged and enforced at the same boundary. Episodes are built from the **already-scrubbed**
`clean` content produced by `_persist_note`'s inputs, never from raw tool arguments. The backfill
command re-runs `scrub` defensively (idempotent) on legacy rows before pushing.

## Testing

- `GraphitiClient`: httpx transport mocked — `add_episode` payload shape, `search` parsing,
  `GraphitiUnavailable` on connection error, health caching.
- `GraphMemoryService`: uuid round-trip (`wizard-note-42` ↔ `("note", 42)`); dual-write swallows
  unavailability; search maps Graphiti hits → `SearchResult`; **fallback path returns the same
  results the existing `hybrid_search` test expects** when the client raises.
- Schema stability: `search` returns unchanged `SearchResponse` in both modes.
- Backfill: idempotent (second run pushes 0 new), scrubs legacy rows, streams in batches.
- No existing test changes required (dual-write is additive; search default `enabled=False`
  keeps legacy path).

## Open questions for KiranOS coordination

These must be agreed so both repos target ONE schema:

1. **Local embedder confirmation** — the stock `zepai/graphiti` image uses `OPENAI_API_KEY`.
   KiranOS must run it with a local LLM/embedder (e.g. `local_graphiti`) or content leaves the
   machine. Wizard assumes local; confirm.
2. **Exact REST endpoints & payload** — the graph service's `add_episode`/`search` HTTP routes
   and request bodies (path, field names, whether `group_id` is per-message or top-level).
   Wizard's `GraphitiClient` will match whatever KiranOS pins.
3. **`group_id` value** — Wizard uses `"wizard"`; KiranOS uses `"kiranos"`. Confirm the literal
   strings and whether unified cross-source recall queries `group_ids=["wizard","kiranos"]`.
4. **uuid namespace convention** — Wizard uses `wizard-{type}-{id}`. Confirm this won't collide
   with KiranOS's uuid scheme in the shared graph.
5. **Service version pin** — which `graphiti-core` / `zepai/graphiti` tag both sides target.

## Out of scope

- Option (a) full cutover (SQLite retained as source-of-truth).
- Changes to any MCP tool signature or `SearchResult`/`SearchResponse` schema.
- Transport changes (stdio MCP + `wizard setup` registration unchanged).
- Communities/reranker tuning on the Graphiti side (KiranOS-owned).
```
