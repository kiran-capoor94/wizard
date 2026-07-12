# Retrieval Recall Engine Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix wizard's weak `search` recall by replacing exact-phrase FTS with OR-of-prefix terms, unioning the vector lane so it can *surface* notes (not just re-rank), adding Porter stemming, and proving it all with a recall benchmark.

**Architecture:** All retrieval logic lives in `src/wizard/repositories/search.py`. Two pure helpers (`_build_fts_query`, `_rrf_fuse`) feed a rewritten `hybrid_search` that runs each entity's BM25 lane plus a threshold-gated cosine lane for notes, fuses lane rankings with Reciprocal Rank Fusion, and trims to `limit`. A new Alembic migration rebuilds the four FTS5 tables with `tokenize='porter unicode61'`. A committed synthetic benchmark and a local real-DB script measure recall before/after.

**Tech Stack:** Python 3.13, SQLModel/SQLAlchemy, SQLite + FTS5 + sqlite-vec, sentence-transformers (all-MiniLM-L6-v2, 384-dim), Alembic, pytest, uv.

## Global Constraints

- Public API unchanged: `SearchRepository.hybrid_search(db, query, limit=10, entity_type=None) -> list[SearchResult]`. `SearchResult` fields (`schemas.py:427`) are unchanged.
- The vector lane MUST stay wrapped in try/except so engines without `vec_note_embeddings` (the `fts_engine` fixture in `tests/scenarios/test_search.py`) degrade to BM25-only — same as today.
- Run tests with `uv run pytest`. FTS-dependent tests use the migrated process-wide engine (`from wizard.database import engine`), created once via `run_migrations()` in `tests/conftest.py`; the `db_engine` fixture uses `create_all()` and has **no** FTS tables — do not use it for search tests.
- Constants: `_RRF_K = 60`, `_POOL_MULTIPLIER = 5`, `_VEC_MAX_DISTANCE = 0.8`.
- Commit after each task. Conventional-commit messages.
- New Alembic migration `down_revision = "69d7ea262b9b"` (current head as of 2026-07-12).

---

## File Structure

- `src/wizard/repositories/search.py` — **modified**. Add `_build_fts_query`, `_rrf_fuse`, `_VEC_MAX_DISTANCE`, `_POOL_MULTIPLIER`, `_RRF_K`; rewrite `hybrid_search` + `_search_notes`; adjust `_search_sessions/_meetings/_tasks` to return `(lanes, results)`; remove now-dead `bm25_score`/`cosine_score`/`_ALPHA`.
- `tests/scenarios/test_search_engine.py` — **new**. Behaviour tests for the rewrite (phrase, multi-term, vec-only union, threshold, graceful degradation).
- `tests/scenarios/test_hybrid_search_repo.py` — **modified**. Drop the three `bm25_score`/`cosine_score` unit tests + import; make the nonexistent-term test deterministic by monkeypatching `embed`→None.
- `src/wizard/alembic/versions/<rev>_fts_porter_stemming.py` — **new** migration.
- `tests/scenarios/test_fts_stemming.py` — **new**. Behaviour test: word-form query matches stemmed content.
- `tests/eval/__init__.py`, `tests/eval/test_search_recall_benchmark.py` — **new**. Synthetic recall benchmark (capstone).
- `scripts/eval_recall_realdb.py` — **new**. Local, non-CI real-DB gut-check.

---

### Task 1: `_build_fts_query` — OR-of-prefix query builder

**Files:**
- Modify: `src/wizard/repositories/search.py`
- Test: `tests/scenarios/test_search_engine.py` (create)

**Interfaces:**
- Produces: `_build_fts_query(query: str) -> str` — returns an FTS5 MATCH string like `"redis"* OR "caching"*`, or `""` when no word characters remain.

- [ ] **Step 1: Write the failing test**

Create `tests/scenarios/test_search_engine.py`:

```python
"""Behaviour tests for the recall-engine rewrite of SearchRepository."""
from wizard.repositories.search import _build_fts_query


def test_build_fts_query_ors_prefix_terms():
    assert _build_fts_query("redis caching decision") == '"redis"* OR "caching"* OR "decision"*'


def test_build_fts_query_splits_on_punctuation():
    assert _build_fts_query("monkey-patch auth!") == '"monkey"* OR "patch"* OR "auth"*'


def test_build_fts_query_empty_when_no_word_chars():
    assert _build_fts_query("   ") == ""
    assert _build_fts_query("!!! ??? ") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_search_engine.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_fts_query'`.

- [ ] **Step 3: Write minimal implementation**

In `src/wizard/repositories/search.py`, add near the top (after imports):

```python
import re

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_search_engine.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/wizard/repositories/search.py tests/scenarios/test_search_engine.py
git commit -m "feat(search): add OR-of-prefix FTS query builder"
```

---

### Task 2: `_rrf_fuse` — Reciprocal Rank Fusion

**Files:**
- Modify: `src/wizard/repositories/search.py`
- Test: `tests/scenarios/test_search_engine.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_rrf_fuse(lanes: list[list[Key]], k: int = _RRF_K) -> dict[Key, float]` where `Key = tuple[str, int]`. Sums `1/(k + rank + 1)` (rank is 0-based) across all lanes per key.

- [ ] **Step 1: Write the failing test**

Append to `tests/scenarios/test_search_engine.py`:

```python
from wizard.repositories.search import _rrf_fuse


def test_rrf_fuse_rewards_agreement_across_lanes():
    # ("note", 1) is rank-0 in both lanes; ("note", 2) is rank-0 in one only.
    lane_a = [("note", 1), ("note", 2)]
    lane_b = [("note", 1), ("note", 3)]
    scores = _rrf_fuse([lane_a, lane_b], k=60)
    assert scores[("note", 1)] > scores[("note", 2)]
    assert scores[("note", 1)] > scores[("note", 3)]


def test_rrf_fuse_surfaces_single_lane_key():
    # A key present in only one lane still gets a positive score (union, not intersect).
    scores = _rrf_fuse([[("note", 5)], [("note", 9)]], k=60)
    assert scores[("note", 9)] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_search_engine.py -v`
Expected: FAIL — `ImportError: cannot import name '_rrf_fuse'`.

- [ ] **Step 3: Write minimal implementation**

In `src/wizard/repositories/search.py`, add after `_build_fts_query`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scenarios/test_search_engine.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/wizard/repositories/search.py tests/scenarios/test_search_engine.py
git commit -m "feat(search): add reciprocal rank fusion helper"
```

---

### Task 3: Rewrite `hybrid_search` for union + RRF + pool

This is the core change. Each lane function returns `(lanes, results)`: a list of ranked `Key` lists and a `Key -> SearchResult` map. Notes contribute two lanes (BM25 + threshold-gated cosine). `hybrid_search` concatenates all lanes, fuses, and trims.

**Files:**
- Modify: `src/wizard/repositories/search.py`
- Modify: `tests/scenarios/test_hybrid_search_repo.py` (remove dead-function tests; deterministic nonexistent-term test)
- Test: `tests/scenarios/test_search_engine.py`

**Interfaces:**
- Consumes: `_build_fts_query`, `_rrf_fuse`, `Key`, `_POOL_MULTIPLIER`, `_VEC_MAX_DISTANCE`; `embed`, `serialize_float32` (existing imports).
- Produces: unchanged public `hybrid_search(db, query, limit=10, entity_type=None) -> list[SearchResult]`. Internal lane helpers now return `tuple[list[list[Key]], dict[Key, SearchResult]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scenarios/test_search_engine.py`:

```python
import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from wizard.models import Note, NoteType
from wizard.repositories.search import SearchRepository


@pytest.fixture
def fts_engine():
    """In-memory engine with FTS5 tables but NO vec table (vec lane must degrade)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5("
            "content, note_type UNINDEXED, content='note', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS note_fts_ai AFTER INSERT ON note BEGIN "
            "INSERT INTO note_fts(rowid, content, note_type) "
            "VALUES (new.id, new.content, new.note_type); END"
        ))
        conn.commit()
    return engine


def test_phrase_reordered_query_still_matches(fts_engine):
    with Session(fts_engine) as db:
        n = Note(note_type=NoteType.DECISION, content="decided on redis caching for the session store")
        db.add(n); db.flush()
        # Old engine required the exact phrase; new engine matches reordered terms.
        results = SearchRepository().hybrid_search(db, "caching redis decision", limit=10)
        assert any(r.entity_id == n.id for r in results)


def test_multi_term_note_outranks_single_term(fts_engine):
    with Session(fts_engine) as db:
        both = Note(note_type=NoteType.INVESTIGATION, content="redis caching layer design")
        one = Note(note_type=NoteType.INVESTIGATION, content="redis connection pool sizing")
        db.add(both); db.add(one); db.flush()
        results = SearchRepository().hybrid_search(db, "redis caching", limit=10)
        ids = [r.entity_id for r in results]
        assert ids[0] == both.id  # hits both terms -> ranks first


def test_vec_lane_degrades_without_vec_table(fts_engine):
    # No vec_note_embeddings in this engine: must not raise, BM25 still works.
    with Session(fts_engine) as db:
        n = Note(note_type=NoteType.DOCS, content="kafka consumer group rebalance notes")
        db.add(n); db.flush()
        results = SearchRepository().hybrid_search(db, "kafka rebalance", limit=10)
        assert any(r.entity_id == n.id for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scenarios/test_search_engine.py -v`
Expected: FAIL — `test_multi_term_note_outranks_single_term` fails (current code wraps the whole query in quotes → `"redis caching"` phrase only matches `both`, so ordering assertion is accidental) and/or behaviour differs. (Phrase-reordered and degrade tests may already error under current phrase-quoting.)

- [ ] **Step 3: Rewrite the implementation**

Replace the body of `hybrid_search` and `_search_notes`, and adjust the other three lane methods, in `src/wizard/repositories/search.py`. Delete `_ALPHA`, `bm25_score`, `cosine_score`. Add `from sqlalchemy import bindparam, text` (keep existing `text` import). Full new versions:

```python
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
                "FROM note WHERE id IN :ids"
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
```

Ensure the module still imports `contextlib`, `datetime`, `text` (existing), and now `bindparam`. Remove the `bm25_score`/`cosine_score`/`_ALPHA` definitions.

- [ ] **Step 4: Fix the two now-broken unit tests in `test_hybrid_search_repo.py`**

The file imports `bm25_score, cosine_score` (now removed) and asserts the nonexistent-term query returns `[]` (the union vec lane could otherwise surface neighbours). Replace its contents with:

```python
"""Behaviour tests for SearchRepository.hybrid_search()."""
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.repositories import search as search_mod
from wizard.repositories.search import SearchRepository


def test_hybrid_search_empty_query_returns_empty():
    repo = SearchRepository()
    with SASession(engine) as db:
        results = repo.hybrid_search(db, "   ")
    assert results == []


def test_hybrid_search_no_results_for_nonexistent_term(monkeypatch):
    # Force embedding off so only BM25 runs -> a truly novel term yields nothing.
    monkeypatch.setattr(search_mod, "embed", lambda _text: None)
    repo = SearchRepository()
    with SASession(engine) as db:
        results = repo.hybrid_search(db, "zzz_nonexistent_xqy_term_9999")
    assert results == []
```

- [ ] **Step 5: Run the full search suite**

Run: `uv run pytest tests/scenarios/test_search_engine.py tests/scenarios/test_hybrid_search_repo.py tests/scenarios/test_search.py tests/scenarios/test_hybrid_search.py -v`
Expected: PASS. (`test_search.py`'s exact-keyword assertions still hold: `"redis"*` etc. match the same single seeded rows; `all_results == 2` holds.)

- [ ] **Step 6: Commit**

```bash
git add src/wizard/repositories/search.py tests/scenarios/test_search_engine.py tests/scenarios/test_hybrid_search_repo.py
git commit -m "feat(search): union BM25+cosine lanes with RRF and vec distance gate"
```

---

### Task 4: Porter stemming migration

Rebuild the four FTS5 tables with `tokenize='porter unicode61'` so word-forms collapse. FTS is a derived index; no base rows are touched.

**Files:**
- Create: `src/wizard/alembic/versions/<rev>_fts_porter_stemming.py`
- Test: `tests/scenarios/test_fts_stemming.py` (create)

**Interfaces:** none (schema migration).

- [ ] **Step 1: Create the migration file**

Create `src/wizard/alembic/versions/b1c2d3e4f5a6_fts_porter_stemming.py` (pick any unused 12-hex revision id; use `b1c2d3e4f5a6`):

```python
"""Rebuild FTS5 tables with Porter stemming.

Revision ID: b1c2d3e4f5a6
Revises: 69d7ea262b9b
Create Date: 2026-07-12 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "69d7ea262b9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (fts table, base table, column DDL, rebuild insert columns, select body)
_TABLES = [
    ("note_fts", "note",
     "content, note_type UNINDEXED, content='note', content_rowid='id'"),
    ("session_fts", "wizardsession",
     "summary, content='wizardsession', content_rowid='id'"),
    ("meeting_fts", "meeting",
     "content, title, content='meeting', content_rowid='id'"),
    ("task_fts", "task",
     "name, content='task', content_rowid='id'"),
]
# Trigger recreation is identical to migration a2b3c4d5e6f7; only the CREATE
# VIRTUAL TABLE gains `tokenize`. Triggers survive the DROP TABLE? No — they
# reference the base tables, not the fts tables, so they persist. We leave the
# existing triggers in place and only rebuild the virtual tables.


def _recreate(conn, tokenize_clause: str) -> None:
    for fts, _base, ddl in _TABLES:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {fts}"))
        conn.execute(sa.text(
            f"CREATE VIRTUAL TABLE {fts} USING fts5({ddl}{tokenize_clause})"
        ))
        conn.execute(sa.text(f"INSERT INTO {fts}({fts}) VALUES('rebuild')"))


def upgrade() -> None:
    conn = op.get_bind()
    _recreate(conn, ", tokenize='porter unicode61'")


def downgrade() -> None:
    conn = op.get_bind()
    _recreate(conn, "")
```

Note: the AFTER INSERT/UPDATE/DELETE triggers created in migration `a2b3c4d5e6f7` fire on the **base** tables and write into the FTS tables by name; dropping and recreating the FTS virtual table (same name) leaves those triggers valid, and `('rebuild')` repopulates from the external-content base table. Confirm during Step 3 that row counts match.

- [ ] **Step 2: Write the failing test**

Create `tests/scenarios/test_fts_stemming.py`:

```python
"""Porter stemming: a query word-form matches a differently-inflected note."""
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories.search import SearchRepository


def test_word_form_variation_matches_after_stemming():
    with SASession(engine) as db:
        n = Note(note_type=NoteType.DECISION,
                 content="we will cache the rendered template fragments")
        db.add(n); db.commit()
        try:
            # "caching" (query) vs "cache" (note) only match if stemmed.
            results = SearchRepository().hybrid_search(db, "caching templates", limit=10)
            assert any(r.entity_id == n.id for r in results)
        finally:
            db.delete(n); db.commit()
```

- [ ] **Step 3: Run test to verify it fails, then passes after migration**

Run: `uv run pytest tests/scenarios/test_fts_stemming.py -v`
Expected initially: the test imports `run_migrations()` via conftest, which upgrades to head. If the new migration is discovered it will already be applied → PASS. To confirm the migration is what makes it pass, first verify the new revision is the head:

Run: `uv run python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; import importlib.resources; d=str(importlib.resources.files('wizard').joinpath('alembic')); c=Config(); c.set_main_option('script_location', d); print(ScriptDirectory.from_config(c).get_heads())"`
Expected: `['b1c2d3e4f5a6']` (single head — no branch).

Then run the stemming test:
Run: `uv run pytest tests/scenarios/test_fts_stemming.py -v`
Expected: PASS.

- [ ] **Step 4: Verify migration up/down + row-count integrity against a scratch DB**

Run:
```bash
cd ~/repos/wizard
uv run python - <<'PY'
import os, tempfile
os.environ["WIZARD_CONFIG_FILE"] = ""  # use defaults
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command
import importlib.resources
tmp = tempfile.mktemp(suffix=".db")
url = f"sqlite:///{tmp}"
d = str(importlib.resources.files("wizard").joinpath("alembic"))
cfg = Config(); cfg.set_main_option("script_location", d); cfg.set_main_option("sqlalchemy.url", url)
command.upgrade(cfg, "head")
eng = create_engine(url)
with eng.begin() as c:
    c.execute(text("INSERT INTO note (note_type, content) VALUES ('INVESTIGATION', 'cache invalidation')"))
    n = c.execute(text("SELECT count(*) FROM note")).scalar()
    f = c.execute(text("SELECT count(*) FROM note_fts")).scalar()
    print("note rows:", n, "note_fts rows:", f)
    assert n == f, "FTS rebuild row-count mismatch"
command.downgrade(cfg, "-1")
command.upgrade(cfg, "head")
print("up/down/up OK")
PY
```
Expected: `note rows: 1 note_fts rows: 1` then `up/down/up OK`.

- [ ] **Step 5: Commit**

```bash
git add src/wizard/alembic/versions/b1c2d3e4f5a6_fts_porter_stemming.py tests/scenarios/test_fts_stemming.py
git commit -m "feat(search): rebuild FTS5 tables with Porter stemming"
```

---

### Task 5: Synthetic recall benchmark (capstone)

A committed, deterministic benchmark that measures `recall@10` and `MRR@10` per failure-mode category. Semantic-only cases use a **deterministic monkeypatched embedding** so CI needs no model download and results are reproducible. Lexical categories need no embeddings.

**Files:**
- Create: `tests/eval/__init__.py` (empty)
- Create: `tests/eval/test_search_recall_benchmark.py`

**Interfaces:**
- Consumes: `SearchRepository.hybrid_search`; `wizard.database.engine` (migrated); `wizard.models`.
- Produces: `run_benchmark(db, repo) -> dict` mapping category → `{"recall_at_10": float, "mrr_at_10": float}` plus an `"aggregate"` key.

- [ ] **Step 1: Write the benchmark + failing thresholds**

Create `tests/eval/__init__.py` (empty) and `tests/eval/test_search_recall_benchmark.py`:

```python
"""Synthetic recall benchmark for SearchRepository.hybrid_search.

Seeds an isolated corpus into the migrated engine, runs labelled queries per
failure mode, and asserts recall@10 / MRR@10 targets. Semantic-only cases use
a deterministic fake embedding (no model download) so CI is reproducible.

Run as a report:  uv run python -m tests.eval.test_search_recall_benchmark
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories import search as search_mod
from wizard.repositories.search import SearchRepository, serialize_float32

# corpus: id-label -> content
CORPUS = {
    "cache": "decided to cache rendered template fragments in redis",
    "pool": "redis connection pool sizing under load",
    "auth": "jwt decoder monkey-patch failed in the auth middleware",
    "kafka": "kafka consumer group rebalance storms during deploy",
    "feline": "the tabby dozed on the woven floor covering",  # semantic-only target
    "noise1": "quarterly budget spreadsheet reconciliation",
    "noise2": "onboarding checklist for new contractors",
}

# category -> list of (query, set of relevant labels)
CASES = {
    "phrase": [("caching redis fragments decided", {"cache"})],       # reordered
    "word_form": [("caching templates", {"cache"}),
                  ("rebalancing consumers", {"kafka"})],              # inflected
    "multi_term": [("redis caching", {"cache"})],                    # most-terms first
    "semantic_only": [("cat on a rug", {"feline"})],                 # no lexical overlap
}

# Deterministic fake embedding space: label/query -> unit-ish vector.
_VECS = {
    "cat on a rug": [1.0] + [0.0] * 383,
    "feline": [1.0] + [0.0] * 383,
}


def _fake_embed(text_in: str):
    return _VECS.get(text_in.strip())


def _seed(db) -> dict[str, int]:
    ids: dict[str, int] = {}
    for label, content in CORPUS.items():
        n = Note(note_type=NoteType.INVESTIGATION, content=content)
        db.add(n); db.flush()
        ids[label] = n.id
    # Seed a matching embedding for the semantic-only target only.
    vec = _VECS["feline"]
    db.execute(
        text("INSERT INTO vec_note_embeddings (note_id, embedding) VALUES (:id, :blob)"),
        {"id": ids["feline"], "blob": serialize_float32(vec)},
    )
    db.commit()
    return ids


def _cleanup(db, ids: dict[str, int]) -> None:
    for nid in ids.values():
        db.execute(text("DELETE FROM vec_note_embeddings WHERE note_id = :id"), {"id": nid})
        db.execute(text("DELETE FROM note WHERE id = :id"), {"id": nid})
    db.commit()


def run_benchmark(db, repo) -> dict:
    ids = _seed(db)
    try:
        out: dict = {}
        all_recall, all_rr = [], []
        for cat, cases in CASES.items():
            recalls, rrs = [], []
            for query, rel_labels in cases:
                rel_ids = {ids[l] for l in rel_labels}
                results = repo.hybrid_search(db, query, limit=10)
                got = [r.entity_id for r in results]
                hit = rel_ids.intersection(got)
                recalls.append(1.0 if hit else 0.0)
                rr = 0.0
                for rank, eid in enumerate(got, start=1):
                    if eid in rel_ids:
                        rr = 1.0 / rank
                        break
                rrs.append(rr)
            out[cat] = {
                "recall_at_10": sum(recalls) / len(recalls),
                "mrr_at_10": sum(rrs) / len(rrs),
            }
            all_recall += recalls; all_rr += rrs
        out["aggregate"] = {
            "recall_at_10": sum(all_recall) / len(all_recall),
            "mrr_at_10": sum(all_rr) / len(all_rr),
        }
        return out
    finally:
        _cleanup(db, ids)


def test_recall_benchmark_meets_targets(monkeypatch):
    monkeypatch.setattr(search_mod, "embed", _fake_embed)
    with SASession(engine) as db:
        metrics = run_benchmark(db, SearchRepository())
    assert metrics["phrase"]["recall_at_10"] >= 0.8
    assert metrics["word_form"]["recall_at_10"] >= 0.8
    # >= 0.5 (target in top 2), not == 1.0: the migrated engine is shared with
    # other scenario tests, so a stray matching note could interleave. The
    # two-term note still ranks well above unrelated single-term hits.
    assert metrics["multi_term"]["mrr_at_10"] >= 0.5
    assert metrics["semantic_only"]["recall_at_10"] >= 1.0  # vec-only surfacing works
    assert metrics["aggregate"]["recall_at_10"] >= 0.8


if __name__ == "__main__":
    from unittest.mock import patch
    with patch.object(search_mod, "embed", _fake_embed), SASession(engine) as db:
        metrics = run_benchmark(db, SearchRepository())
    print(f"{'category':<16}{'recall@10':>12}{'mrr@10':>10}")
    for cat, m in metrics.items():
        print(f"{cat:<16}{m['recall_at_10']:>12.2f}{m['mrr_at_10']:>10.2f}")
```

- [ ] **Step 2: Capture the BEFORE baseline (evidence)**

Measure the pre-change engine in an isolated worktree so nothing in the main tree moves. This is a one-time measurement, not a code change.

```bash
cd ~/repos/wizard
PRE=$(git rev-parse HEAD~2)                 # T2 — before Task 3 (search rewrite) and Task 4 (stemming)
git worktree add /tmp/wizard-baseline "$PRE"
# Copy the benchmark file into the old checkout so it can run against old search.py:
mkdir -p /tmp/wizard-baseline/tests/eval
cp tests/eval/__init__.py tests/eval/test_search_recall_benchmark.py /tmp/wizard-baseline/tests/eval/
cd /tmp/wizard-baseline && uv run python -m tests.eval.test_search_recall_benchmark
```
Expected: `phrase` and `word_form` recall near 0.0 (the bug). Copy that table into a `# BASELINE (pre-fix):` comment block at the top of `tests/eval/test_search_recall_benchmark.py`. Then clean up:

```bash
cd ~/repos/wizard && git worktree remove /tmp/wizard-baseline
```

- [ ] **Step 3: Run the benchmark test**

Run: `uv run pytest tests/eval/test_search_recall_benchmark.py -v`
Expected: PASS.

Run the report form:
Run: `uv run python -m tests.eval.test_search_recall_benchmark`
Expected: a table with `phrase`, `word_form`, `multi_term`, `semantic_only`, `aggregate` all at high recall.

- [ ] **Step 4: Commit**

```bash
git add tests/eval/__init__.py tests/eval/test_search_recall_benchmark.py
git commit -m "test(search): add synthetic recall benchmark with before/after evidence"
```

---

### Task 6: Local real-DB gut-check script

A throwaway script (not run in CI) that runs hand-authored queries against the real `~/.wizard/wizard.db`, read-only, and prints results so Kiran can feel the improvement on his own memory.

**Files:**
- Create: `scripts/eval_recall_realdb.py`

**Interfaces:** none (CLI script).

- [ ] **Step 1: Write the script**

Create `scripts/eval_recall_realdb.py`:

```python
"""Local recall gut-check against the real ~/.wizard/wizard.db (READ-ONLY).

Not part of CI. Fill QUERIES with things you'd actually search for, plus a
substring you expect to see in a relevant note's snippet. Run:

    uv run python scripts/eval_recall_realdb.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session

from wizard.repositories.search import SearchRepository

# (query, expected substring in a relevant result's snippet) — edit these.
QUERIES: list[tuple[str, str]] = [
    ("search recall", "bm25"),
    ("wizard memory noise", "note"),
]

DB = Path.home() / ".wizard" / "wizard.db"


def main() -> int:
    if not DB.exists():
        print(f"No DB at {DB}; nothing to check.")
        return 0
    engine = create_engine(f"sqlite:///{DB}?mode=ro", connect_args={"uri": True})
    repo = SearchRepository()
    with Session(engine) as db:
        for query, expect in QUERIES:
            results = repo.hybrid_search(db, query, limit=10)
            hit = any(expect.lower() in (r.snippet or "").lower() for r in results)
            mark = "HIT " if hit else "miss"
            print(f"[{mark}] {query!r} -> {len(results)} results "
                  f"(expected snippet ~{expect!r})")
            for r in results[:5]:
                print(f"        {r.entity_type}#{r.entity_id}: {r.snippet[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the real DB**

Run: `uv run python scripts/eval_recall_realdb.py`
Expected: prints a HIT/miss table (content depends on Kiran's real notes). Note: the sqlite-vec extension may not load on a read-only ad-hoc engine; the vec lane will degrade to BM25-only, which is fine for a lexical gut-check.

- [ ] **Step 3: Commit**

```bash
git add scripts/eval_recall_realdb.py
git commit -m "chore(search): add local real-DB recall gut-check script"
```

---

## Final verification

- [ ] Run the whole suite: `uv run pytest -q`
  Expected: all pass (pay attention to `tests/scenarios/test_*search*`, `test_fts_stemming`, `tests/eval/`).
- [ ] Report form prints healthy numbers: `uv run python -m tests.eval.test_search_recall_benchmark`.
- [ ] `uv run python scripts/eval_recall_realdb.py` runs against the real DB.

---

## Self-Review notes (author)

- **Spec coverage:** Section 1a → Task 1 + Task 3; 1b union/RRF → Task 2 + Task 3; 1b-note vec threshold → Task 3 (`_VEC_MAX_DISTANCE`); 1c pool → Task 3 (`_POOL_MULTIPLIER`); Section 2 stemming → Task 4; Section 3 synthetic benchmark → Task 5; Section 3 real-DB script → Task 6. All covered.
- **Deferred (out of scope, no task — correct):** Amplifier B (multi-entity embeddings), Phase 2 write-side, Phase 3 adoption.
- **Type consistency:** `Key = tuple[str, int]` used identically in Tasks 2–3; lane helpers uniformly return `tuple[list[list[Key]], dict[Key, SearchResult]]`; `hybrid_search` signature unchanged throughout.
- **Known risk to watch during Task 4:** confirm the FTS sync triggers from migration `a2b3c4d5e6f7` still fire after the virtual tables are dropped/recreated (they target base tables, so they should) — Step 4's row-count assertion is the guard.
