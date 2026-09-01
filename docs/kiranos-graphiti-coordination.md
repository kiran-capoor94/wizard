# Wizard ↔ KiranOS: shared Graphiti contract

> ## ⚠️ Correction (2026-08-31) — the uuid contract below is wrong
>
> Everything in this document about deterministic episode uuids was tested live
> against the pinned image and **does not work**. Both sides have been changed.
>
> **What we assumed:** sending `uuid: "wizard-note-42"` on `POST /messages`
> upserts an episode, giving idempotent backfill, and search returns those
> uuids so each side can map results back to its own rows.
>
> **What actually happens** in graphiti-core 0.22.0:
>
> 1. `add_episode(uuid=...)` is an **update selector**, not an idempotency key.
>    `graphiti.py:368` does `EpisodicNode.get_by_uuid(uuid)` and raises
>    `NodeNotFoundError` when the episode does not already exist.
> 2. That exception escapes `graph_service`'s `worker()` and **kills the single
>    async ingest consumer for the life of the process**. Every subsequent
>    `POST /messages` still returns `202 Accepted` into a queue nothing reads.
>    This is silent — no error is returned to the caller.
> 3. `POST /search` returns **edge (fact) uuids**, never episode uuids. So a
>    deterministic episode uuid was never reachable from the read path anyway.
>
> Verified live: with a uuid, zero nodes are created and ingest stays dead until
> the container restarts; without one, the episode and its entities extract
> normally.
>
> **The corrected contract:** neither side sends `uuid`. The namespaced identity
> travels in the episode **`name`** (`wizard-{type}-{id}`, `kiranos:{kind}:{id}`),
> which Graphiti persists on the Episodic node, plus `source_description`.
>
> **Consequence — backfill is no longer idempotent.** Re-running it creates
> duplicate episodes. Clear the partition first (`DELETE /group/{group_id}`) for
> a clean rebuild.
>
> **The read path was already correct.** An earlier revision of this note
> claimed it needed redesign. It did not: `fact_to_search_result` has always
> mapped a hit to a fact-level result (`entity_type="fact"`, `entity_id=None`)
> and never read `results[].uuid`. Only the now-deleted `parse_episode_uuid`
> helper encoded the wrong assumption, and nothing called it.
>
> A graph hit therefore cannot be resolved back to a Wizard row, and that is
> the intended behaviour rather than a gap — facts are surfaced as facts.
> Do not reintroduce uuid parsing on the read path; a regression test in
> `tests/test_graph_memory.py` pins this.

> ## ⚠️ Correction 2 — timestamps must be timezone-aware
>
> Wizard was sending naive `reference_time` (its SQLite timestamps come from
> `datetime.now()` — local, no tzinfo). Graphiti then stored a naive `valid_at`,
> and `retrieve_episodes` — which compares against `datetime.now(timezone.utc)`
> — never matched them.
>
> Two consequences, both silent:
>
> 1. `GET /episodes/{group_id}` returned `[]` for the wizard partition even
>    with episodes present, so there was no way to tell what had been ingested.
> 2. `add_episode`'s own previous-episodes lookup was always empty, so every
>    episode was extracted with **no prior context and no entity resolution
>    against earlier episodes** — a quietly degraded graph.
>
> Verified live: KiranOS episodes (which carry `Z`-suffixed timestamps) were
> returned by `GET /episodes`; Wizard's were not.
>
> Wizard now normalises to UTC at the client boundary
> (`integrations.graphiti._as_utc`). **KiranOS should confirm it always sends
> tz-aware timestamps** — it appears to, but it is now a contract requirement
> rather than an accident.
>
> Note that episodes written before this fix remain invisible to
> `retrieve_episodes`. The wizard partition was cleared once to start clean.

## The original 5 open questions (answered, except as corrected above)

**From:** Wizard side (PR [#57](https://github.com/kiran-capoor94/wizard/pull/57), branch `feat/graphiti-shared-substrate`)
**Re:** the shared Graphiti temporal knowledge graph both systems will read/write
**Status:** Wizard's integration is built, tested (335 passing), and **shipped disabled** (`settings.graphiti.enabled=false`). It won't touch the graph until you confirm the contract below and we flip the flag. The whole wire shape is isolated in one file (`integrations/graphiti.py`), so finalizing any of this is a one-file change on our side — no rework.

## What Wizard is committing to (so you can design against it)

- Wizard talks to Graphiti's **REST graph service** (`zepai/graphiti`, default `http://localhost:8000`, configurable via `GRAPHITI_URL`) — **not** the MCP server.
- Everything Wizard writes goes in under **`group_id: "wizard"`**. We assume you write yours under `group_id: "kiranos"`.
- Wizard writes **one episode per note / session-close / meeting**, as `EpisodeType.json`, with a **deterministic, idempotent uuid** `wizard-{type}-{id}` and `reference_time = created_at`.
- **All content is PII-scrubbed before it leaves Wizard.** Scrubbing is Wizard's invariant; you receive already-clean text.
- Wizard **reads** the graph only for its `search` tool, querying `group_ids: ["wizard"]`. If the graph is unreachable it silently falls back to its local engine — so an outage on your side never breaks Wizard.

### The exact payloads Wizard currently emits (our best-guess shapes — please confirm or correct)

**Write** — `POST /messages`:
```json
{
  "group_id": "wizard",
  "messages": [{
    "content": "<scrubbed JSON episode body, see below>",
    "role_type": "user",
    "role": "wizard",
    "name": "note 42",
    "timestamp": "2026-07-28T12:00:00",
    "source_description": "wizard:note",
    "uuid": "wizard-note-42"
  }]
}
```

**Search** — `POST /search`:
```json
{ "query": "db lock contention", "group_ids": ["wizard"], "max_facts": 10 }
```
→ Wizard reads `response.results[].uuid`, parses `wizard-{type}-{id}`, and fetches display fields from its own SQLite. **We only need the uuids back in rank order.**

**Health** — `GET /health` (used for the reachability probe).

**Episode bodies** (the `content` field, structured JSON — types preserved as properties):
```jsonc
// note      → { "kind":"note", "note_type":"DECISION", "content":..., "mental_model":..., "task_id":..., "session_id":..., "supersedes":"wizard-note-39" }
// session   → { "kind":"session", "intent":..., "state_delta":..., "open_loops":[...], "next_actions":[...], "closure_status":"clean" }
// meeting   → { "kind":"meeting", "title":..., "category":..., "content":..., "summary":... }
```

---

## The 5 questions we need answered

### 1. Local embedder — confirm no data leaves the machine
The stock `zepai/graphiti` image uses `OPENAI_API_KEY` for entity extraction **and embeddings**, which would send every episode body to OpenAI. That breaks the local-first constraint (even though our content is PII-scrubbed, it's still ours). **Are you running the graph service with a fully local LLM/embedder** (e.g. `local_graphiti` / Ollama), no `OPENAI_API_KEY`? If not, we need to talk before enabling — this is the one item that gates whether we can turn Wizard's side on at all.

### 2. Exact REST routes + payload field names
Please confirm (or give us the real shapes for):
- **Write:** is it `POST /messages` with a top-level `group_id` + a `messages: [...]` array, each message carrying `content` / `timestamp` / `uuid` / `source_description`? Or a different route/body (e.g. `POST /episodes` with `episode_body`, `reference_time`, `source=json`, `group_id`, `uuid` mapping straight to `graphiti_core.add_episode`)?
- **Search:** is it `POST /search` with `query` + `group_ids` + `max_facts`? What's the response envelope, and **does each result carry the episode `uuid`** (we key on that) or only extracted-fact text?
- **Health:** is `GET /health` the right liveness probe?

### 3. `group_id` literals + cross-source recall
- Confirm the literals: Wizard writes/reads **`"wizard"`**, KiranOS **`"kiranos"`** — agreed?
- For **unified cross-source recall**, is the intent that a query passes `group_ids: ["wizard", "kiranos"]` to search both partitions at once? If so, whose component issues those cross-source queries — KiranOS's agent-facing MCP, or does Wizard also need to widen its `group_ids` on some path?

### 4. uuid namespace — collision-free
Wizard uses `wizard-{type}-{id}` (e.g. `wizard-note-42`, `wizard-session-5`, `wizard-meeting-8`). Confirm your uuids are prefixed such that they **can never collide** with ours in the shared graph (e.g. `kiranos-idea-9`). Wizard's parser already drops any uuid not starting with `wizard-` + a known type, so foreign nodes are safely ignored on our read path — we just need yours to never accidentally look like ours.

### 5. Version pin
Which **`graphiti-core` / `zepai/graphiti` image tag** are both sides targeting? Pinning one version avoids a payload-shape drift between our client and your service. Please name the tag you're deploying so we pin our client's assumptions to it.

---

## What happens after you answer

1. We reconcile `integrations/graphiti.py` to your confirmed routes/payloads (one file, ~65 lines).
2. We stand up the graph service locally, run `wizard backfill-graphiti` to push existing history under `group_id="wizard"`.
3. We flip `settings.graphiti.enabled=true` and validate `search` against the live graph.

Reference on our side: design `docs/spec-graphiti-shared-substrate.md`, PR #57.

---

# Wizard's reply — reconciled against your answers (2026-07-28)

Thanks — the three discrepancies you flagged were exactly the kind of thing we needed before enabling. All handled on our side; one item is now yours. Cross-checked your claims against Graphiti's own source (the REST graph_service wraps `graphiti.search()` → returns edges/facts; `retrieve_episodes`/`get_by_uuids` are the episode-keyed paths) — your account is correct.

**1. Local embedder** — ✅ understood. We'll set `OPENAI_BASE_URL` for the embedder exactly as you do, use a non-reasoning instruct model, and verify via logs on first live run. No action needed from you.

**2a. `/search` returns `{facts:[…]}` not `{results:[…]}`** — ✅ fixed. Our client reads `data["facts"]`.

**2b. Search returns fact uuids, not episode uuids** — ✅ this was the big one, and we changed our design because of it. Our `search` tool now returns **fact-level results** in graphiti-mode: each Graphiti fact becomes a `SearchResult` with `entity_type="fact"`, `entity_id=null`, `snippet=<fact text>`, `title=<fact name>`, `created_at=<valid_at>`. We are NOT trying to round-trip back to our SQLite rows off `/search` anymore. (We noted `retrieve_episodes`/`get_nodes_and_edges_by_episode` *would* give us episode-uuid round-trips if you ever expose that route — but we've chosen fact-level as the simpler, more graph-native path and don't need you to add anything.) Our SQLite fallback still returns row-level results with real ids, unchanged.

**2c. Health is `/healthcheck` not `/health`** — ✅ fixed.

**3. Cross-source recall** — ✅ agreed. You own the `group_ids:["wizard","kiranos"]` unified query; we stay `["wizard"]`. No change on our side.

**4. uuid namespace** — ✅ confirmed collision-free (our `wizard-note-42` hyphen vs your `kiranos:idea:9` colon). Noted the deterministic-uuid / poisoned-AsyncWorker fragility — we'll treat `docker compose down -v` as the recovery for a wedged local graph during dev.

**5. Version pin** — 🔜 **over to you.** We don't have a `graphiti-core` tag pinned on our side yet either (our client was built against your best-guess shapes, now corrected). Please resolve the concrete image digest / `graphiti-core` version your validated stack ran against and send it — we'll pin our client's assumptions to that exact version in one go.

**Where that leaves us:** our side is code-complete and green behind `enabled=false`. We can stand up the local graph service, run `wizard backfill-graphiti` under `group_id="wizard"`, and live-probe `/search` to confirm the fact shape end-to-end whenever. We hold the flag off until (5) is pinned and the probe passes.

---

# Joint live test — post-mortem + our fix (2026-07-28)

The joint test didn't reach the cross-source recall proof, but it did its job: found a real, actionable failure at low blast radius, both sides recovered clean, zero data loss.

**Proved before the crash:** ✅ contract is live-correct (our read probe saw `kiranos` facts + an empty `wizard` partition; the reconciled `/search` shape works); ✅ namespace isolation held; ✅ recall works post-recovery.

**True root cause (your container inspection — corrects our earlier "AsyncWorker deadlock" guess):** **OOMKilled, exit 137.** `/messages` returns 202 instantly (server queues internally), so our backfill's synchronous loop fired 3,200+ episodes with no backpressure → Graphiti buffered them in an unbounded in-memory queue → the single serial worker (bottlenecked on local nemotron) couldn't drain → OOM → SIGKILL. Recovery was `docker compose up -d graph` — Neo4j survived, `down -v` NOT needed, `kiranos` facts intact.

**Our fix (done, reviewed, committed — 354 tests green):**
- **Rate-limited the backfill** — pushes in batches (`backfill_batch_size`, default 25) with a pause between (`backfill_pause_seconds`, default 5s) so submission rate ≤ drain rate. Both config-tunable.
- **Split read/write timeouts** — `/messages` writes get `write_timeout_seconds` (30s) vs the 2s read timeout that had wrongly flagged slow-but-alive writes as unavailable. (The timeout was a correctness fix, not the OOM cause — pacing is what prevents the OOM, since 202 returns instantly regardless of our timeout.)

**Your half (the real shared-substrate robustness gap):** the graph service needs a **bounded ingest queue** so *any* fast producer (us, KiranOS, a future third source) can't OOM the shared service. A producer-side throttle (ours) is necessary but not sufficient. Flagging as yours.

**Proposed rerun (staged):** once you've got the bounded queue (or confirm the container survives our throttled rate), we rerun the throttled backfill — starting with a **small staged push** (a few hundred episodes), watch memory, then run to the full ~6.6k. Container's up and clean now. **What episodes/min can your serial worker sustain?** We'll tune `backfill_pause_seconds` to it.
