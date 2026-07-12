# Spec — Retrieval Recall Engine Overhaul

**Task:** unassigned (track in wizard as an `investigation`→`decision` chain once implementation starts)
**Status:** Approved design, ready to implement.
**Last updated:** 2026-07-12
**Scope:** Thread E, Phase 1 of 3 ("engine-first, staged"). Phases 2 (write-side signal quality) and 3 (adoption ergonomics) are deferred to their own specs.

---

## Problem Statement

Wizard's memory loop is caught in a self-reinforcing decline:

> **Notes are noise** (vague / duplicate / mistyped writes) → **recall is weak** (retrieval surfaces junk or misses the good note) → **trust erodes** → **the tool gets skipped** → less signal goes in → notes get noisier.

The three symptoms are one loop, and **recall is the keystone**: raise the payoff of retrieval and the write-discipline and adoption fixes (Phases 2–3) become worth paying for. Fix write/adoption first and you are only feeding a broken retriever.

This spec fixes retrieval. There are three concrete, code-level root causes:

1. **Exact-phrase query wrapper.** `repositories/search.py:46` wraps the whole query in double quotes (`fts_query = f'"{sanitised}"'`), forcing FTS5 to require the **entire query as a literal phrase, in order**. `search("redis caching decision")` only matches a note containing that exact three-word phrase. Any reordering or partial-term overlap misses.

2. **The semantic lane cannot expand recall.** `repositories/search.py:112-114` iterates only over the BM25 candidate set; cosine similarity **re-ranks BM25 hits but can never surface a note BM25 missed**. The `torch`/`sentence-transformers` embedding dependency is effectively decorative for recall. Semantically-relevant notes with no literal keyword overlap are unreachable.

3. **No stemming.** The FTS5 tables (`alembic/versions/a2b3c4d5e6f7_add_fts5_search_tables.py`) are created with the default tokenizer — no `tokenize=` clause. So "caching" ≠ "cache", "decisions" ≠ "decision". Stacked on cause (1), recall is gated **twice**: exact phrase **and** exact word-form.

Additionally, sessions/meetings/tasks have **no vector lane at all** (BM25-only) — noted here but addressed in a deferred amplifier, not this spec's core.

The intelligence tools (`what_should_i_work_on`, `what_am_i_missing`, `task_start`, `session_start` ordering) do **not** use `search` — they rank off precomputed `task_state` counters. They are out of scope; this spec touches only the `search` retrieval path.

---

## Design

Three sections. Sections 1 and 2 are in scope for this spec; Section 3 measures both and gates the deferred Amplifier B.

### Section 1 — `search.py` core redesign (pure-Python, no schema change)

**1a. Replace the phrase wrapper with a term-OR query builder.**

New helper `_build_fts_query(query: str) -> str`:
- Tokenize the sanitised query on non-word boundaries; drop empties.
- For each term, escape internal double-quotes and emit a quoted prefix token: `"term"*`.
- Join terms with ` OR `.
- If no terms survive, caller returns `[]` (unchanged guard).

Example: `redis caching decision` → `"redis"* OR "caching"* OR "decision"*`. Quoting isolates each term from FTS5 operators embedded in user input; the `*` restores prefix matching (which the current code strips). BM25 rank naturally floats notes hitting more/stronger terms to the top, so switching AND→OR does not flood the top of the list with weak single-term hits.

**1b. True union hybrid via Reciprocal Rank Fusion (RRF), replacing the weighted re-rank.**

- Each lane is an **independent candidate generator** returning an *ordered* list of `(key, SearchResult)` where `key = (entity_type, entity_id)`.
- Notes run **two** lanes: BM25 over `note_fts`, and cosine over `vec_note_embeddings` (unchanged SQL, but now its results are unioned, not discarded when BM25-absent).
- Sessions/meetings/tasks run their single BM25 lane (still benefit from 1a + Section 2).
- Fusion: `_rrf_fuse(lanes, k=60)` → `score(key) = Σ_lanes 1/(k + rank_in_lane)`. Sort by score desc; return top `limit` `SearchResult`s.
- Delete `_ALPHA` and the `bm25_score`/`cosine_score`→weighted-sum blend. RRF is scale-free, so no hand-tuned reconciliation between BM25 rank and cosine distance. (Keep `bm25_score`/`cosine_score` only if still needed elsewhere; otherwise remove.)

This is the fix for root cause (2): a note found **only** by the vector lane now receives an RRF contribution and can appear in results.

**1b-note — vec-lane distance threshold (refinement found during planning).** Because cosine KNN *always* returns nearest neighbours, an unconstrained union would make even a nonsense query return the corpus's closest notes (breaking `test_hybrid_search_no_results_for_nonexistent_term` and hurting precision). Gate the vec lane with `_VEC_MAX_DISTANCE = 0.8` (cosine distance, 0–2 scale): after fetching the pool ordered by distance, keep only rows with `distance < _VEC_MAX_DISTANCE` before they enter the lane. Filtered in Python (sqlite-vec KNN needs its own `LIMIT k`, so no SQL `WHERE distance` clause). Genuine paraphrase matches sit well under 0.8; unrelated notes sit above it. The exact cutoff is a knob the eval harness (Section 3) can tune.

**1c. Widen the candidate pool before the merge.**

- Introduce `_POOL_MULTIPLIER = 5`. Each lane fetches `limit * _POOL_MULTIPLIER` rows (`LIMIT` in each SQL query), fusion runs over the wider pool, then the merged result is trimmed to `limit`.
- Fixes per-lane crowding: in a mixed `entity_type=None` search, a flood of note hits can no longer starve sessions/meetings out of the top `limit` before they are even considered.

**Files touched:** `src/wizard/repositories/search.py` only.

### Section 2 — Amplifier A: Porter stemming (in scope)

New Alembic migration (`alembic/versions/`):
- **Upgrade:** drop the four FTS5 tables (`note_fts`, `session_fts`, `meeting_fts`, `task_fts`) and their six-per-table sync triggers; recreate each with `tokenize="porter unicode61"` (external-content config otherwise identical); recreate the triggers; repopulate each from its base table via the FTS5 rebuild command (`INSERT INTO note_fts(note_fts) VALUES('rebuild')`, etc.).
- **Downgrade:** symmetric — recreate the tables without the `tokenize=` clause and rebuild.
- FTS is a **derived index** — no source rows are touched, so this is low-risk and fully reversible.
- Collapses word-forms (cache/caching/cached, decision/decisions) across **all** entity types, compounding with Section 1a.

**Files touched:** one new migration file; migration test.

### Section 3 — Eval harness (in scope; gates deferred Amplifier B)

**Metrics:** `recall@10` (did the relevant note make the cut — the broken thing) and `MRR@10` (how near the top). Reported per-query, per-category, and aggregate.

**Committed synthetic benchmark** — `tests/eval/test_search_recall_benchmark.py` (built on `tests/fakes.py` + `tests/scenarios/` infra). Seeds a fixture DB of ~20 notes with known content and ~12 labeled `(query, relevant_note_ids)` cases, one per failure mode:
- *phrase* — query is a reworded/reordered version of a note → exercises root cause (1).
- *word-form* — query "caching", note "cache" → exercises root cause (3).
- *semantic-only* — query shares **no** keywords with the note, only meaning → exercises root cause (2), and **quantifies whether Amplifier B is worth building**.
- *multi-term* — the note hitting the most terms must rank highest (guards against 1a over-broadening).

Assertions: word-form and phrase categories rise from ~0 to `recall@10 ≥ 0.8`; multi-term ordering preserved; aggregate `recall@10` and `MRR@10` strictly beat a recorded pre-change baseline (regression guard). A `--report` mode prints the before/after table.

**Local real-DB gut-check** — `scripts/eval_recall_realdb.py` (not run in CI; skips cleanly if the DB is absent). Opens `~/.wizard/wizard.db` **read-only**, runs a small hand-authored list of `(query, expected-note substrings)` that Kiran fills with queries he'd actually type, and prints the old-engine vs new-engine result table. Confirms the improvement is felt on real memory, not just a fixture.

---

## Success Criteria

- Synthetic benchmark: word-form and phrase categories go from ~0 to `recall@10 ≥ 0.8`; semantic-only recall is measured and reported (the number that decides Amplifier B); multi-term top-1 unchanged; aggregate `recall@10`/`MRR@10` strictly exceed the recorded baseline.
- All existing search tests pass unchanged: `tests/scenarios/test_hybrid_search.py`, `test_hybrid_search_repo.py`, `test_search.py`, `test_embedding_write.py`, `test_vec_table.py`.
- Migration applies and reverses cleanly; post-migration each `*_fts` row count equals its base-table row count (rebuild populated correctly).
- `scripts/eval_recall_realdb.py` runs against the real DB and prints a before/after table.

---

## Out of Scope (deferred)

- **Amplifier B — embeddings for sessions/meetings/tasks.** New `vec_*_embeddings` tables, backfill, and write-path wiring (`ingest_meeting`, `session_end`, `create_task`). Gated on the *semantic-only* recall number from Section 3 — if Section 1+2 already deliver the recall you want on notes, B may not earn its complexity. Its own spec.
- **Phase 2 — write-side signal quality.** Activate the dormant `note.status` / `supersedes_note_id` machinery so wrong/outdated notes get demoted; near-duplicate dedup beyond exact `content_hash`; curb the `stop.sh` `OBSERVATION` firehose and tune session-end transcript synthesis. Directly attacks "notes are noise."
- **Phase 3 — adoption ergonomics.** Make save/recall cheaper and more automatic so the tool stops getting skipped.
- The other brainstorm threads (A tighten existing skills, B trend research, C new-skill gaps, D skill interoperability) are separate sessions.

---

## Risks & Notes

- **RRF discards absolute scores.** `SearchResult` exposes no numeric score field, so ranking-only fusion changes nothing observable downstream. If a score is ever surfaced, expose the RRF score.
- **Vec lane always returns neighbours.** Mitigated by the `_VEC_MAX_DISTANCE` gate (1b-note); the vec lane must remain wrapped in try/except so engines without `vec_note_embeddings` (e.g. the `fts_engine` test fixture) degrade to BM25-only, as today.
- **Porter over-stemming** (e.g. "universal"→"univers") can create occasional loose matches; acceptable for a single-user recall tool, and RRF de-emphasises weak hits.
- **Short-term prefix matches** (`"a"*`) broaden results; RRF ranking absorbs this, and terms this short are rare in real queries.
- **Migration rebuild cost** is trivial on a single-user local DB.
