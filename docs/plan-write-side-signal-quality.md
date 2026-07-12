# Write-Side Signal Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give wizard notes an "immune system" — stop machine boilerplate at intake, harden/scrub/dedup the OBSERVATION firehose, and activate the dormant `status` demotion lifecycle so demoted notes vanish from recall.

**Architecture:** Stage 2a is a pure write-side quality gate (a shared `note_hashing` helper, a one-line skip in the session auto-closer, and a hardened Stop-hook). Stage 2b wires the existing `note.status` column into recall via opt-in `active_only` read filters plus a new deliberate `mark_note` MCP tool. Stage 3 adds behaviour tests and a read-only noise-audit script.

**Tech Stack:** Python 3.13, SQLModel/SQLAlchemy, SQLite, FastMCP (Depends-injected repos), pytest, uv.

## Global Constraints

- `active` is the **sole recall-eligible status**. Recall excludes superseded, contradicted, invalid, archived, and unclassified. The filter is literally `status == 'active'`.
- Read-side `active_only` params default to **`False`** (no existing caller changes behaviour); only the named recall callers pass `True`. `rewind_task` keeps `active_only=False` (full history).
- No schema migration. The `status`, `supersedes_note_id`, `reference_count` columns already exist (server_default `active`/`NULL`/`0`).
- Run tests with `uv run pytest`. FTS/vec-dependent tests use the migrated process-wide engine (`from wizard.database import engine`); conftest runs migrations to head at import.
- `mark_note` convention: `supersedes_note_id` lives on the **winning** note. `mark_note(note_id, 'superseded', superseded_by_note_id=W)` sets `note[note_id].status='superseded'` AND `note[W].supersedes_note_id = note_id`.
- Commit after each task, conventional messages. `git add` only the files a task changed — never `git add -A` (a stray `uv.lock` drift exists in the tree).

---

## File Structure

- `src/wizard/note_hashing.py` — **new**. `normalize_for_hash(text)` + `content_hash(text)`; shared by save_note and the Stop-hook so dedup is consistent.
- `src/wizard/tools/task_tools.py` — **modify** `_prepare_note_fields` to hash via `note_hashing.content_hash`.
- `src/wizard/services.py` — **modify** `SessionCloser` to skip the synthetic boilerplate note.
- `src/wizard/cli/hooks.py` — **modify** the OBSERVATION write: scrub + normalized `content_hash` + dedup.
- `src/wizard/repositories/note.py` — **modify** `get_for_task` / `get_notes_grouped_by_task` (add `active_only`); **add** `set_status`.
- `src/wizard/tools/task_tools.py`, `tools/query_tools.py`, `tools/session_tools.py` — **modify** recall callers to pass `active_only=True`.
- `src/wizard/repositories/search.py` — **modify** the note metadata fetch to filter `status='active'`.
- `src/wizard/tools/note_tools.py` — **add** `mark_note` tool; register it.
- `src/wizard/tools/__init__.py` — **modify** to import/register/export `mark_note`.
- `src/wizard/schemas.py` — **add** `MarkNoteResponse`.
- `src/wizard/skills/note*` — **modify** the note skill (teach `mark_note`).
- `scripts/audit_note_quality.py` — **new**. Read-only corpus-health report.
- Tests under `tests/scenarios/` (+ existing `test_stop_hook.py`).

---

### Task 1: Shared normalized content-hash helper

**Files:**
- Create: `src/wizard/note_hashing.py`
- Modify: `src/wizard/tools/task_tools.py` (`_prepare_note_fields`)
- Test: `tests/scenarios/test_note_hashing.py` (create)

**Interfaces:**
- Produces: `normalize_for_hash(text: str) -> str` (strip + collapse internal whitespace to single spaces); `content_hash(text: str) -> str` (sha256 hex of the normalized text). Consumed by Task 3 (hooks) and `_prepare_note_fields`.

- [ ] **Step 1: Write the failing test**

Create `tests/scenarios/test_note_hashing.py`:

```python
from wizard.note_hashing import content_hash, normalize_for_hash


def test_normalize_collapses_whitespace_and_strips():
    assert normalize_for_hash("  a   b\n c \t") == "a b c"


def test_content_hash_ignores_whitespace_variation():
    assert content_hash("redis  caching\n") == content_hash("redis caching")


def test_content_hash_is_case_sensitive():
    # keep case — distinct content must not collapse
    assert content_hash("Cache") != content_hash("cache")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_note_hashing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wizard.note_hashing'`.

- [ ] **Step 3: Create the module**

Create `src/wizard/note_hashing.py`:

```python
"""Normalized content hashing for note dedup — shared by save_note and the Stop hook."""
from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def normalize_for_hash(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip ends.

    Case is preserved so genuinely distinct content does not collapse.
    """
    return _WS_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """SHA-256 hex of the normalized content."""
    return hashlib.sha256(normalize_for_hash(text).encode()).hexdigest()
```

- [ ] **Step 4: Rewire `_prepare_note_fields` to use it**

In `src/wizard/tools/task_tools.py`, add to the imports near the top:

```python
from ..note_hashing import content_hash as compute_content_hash
```

Then in `_prepare_note_fields` replace the hash line:

```python
    content_hash = hashlib.sha256(clean.encode()).hexdigest()
```
with:
```python
    content_hash = compute_content_hash(clean)
```

(Leave the existing `import hashlib` if it is used elsewhere in the file; if `hashlib` becomes unused, remove that import.)

- [ ] **Step 5: Add a dedup behaviour test**

Append to `tests/scenarios/test_note_hashing.py`:

```python
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType, Task, TaskState
from wizard.repositories.note import NoteRepository


def test_whitespace_variant_note_dedups_by_hash():
    from wizard.note_hashing import content_hash
    repo = NoteRepository()
    with SASession(engine) as db:
        t = Task(name="dedup-hash-task"); db.add(t); db.flush()
        db.add(TaskState(task_id=t.id)); db.flush()
        h = content_hash("finding X")
        n1 = Note(note_type=NoteType.INVESTIGATION, content="finding X",
                  task_id=t.id, content_hash=h, artifact_id=f"t{t.id}", artifact_type="task")
        db.add(n1); db.commit()
        try:
            # a whitespace-variant produces the SAME hash → dedup lookup finds n1
            assert content_hash("finding   X\n") == h
            hit = repo.get_by_content_hash(db, t.id, content_hash("finding   X\n"))
            assert hit is not None and hit.id == n1.id
        finally:
            db.delete(n1); db.execute(text("DELETE FROM task_state WHERE task_id=:i"), {"i": t.id})
            db.delete(t); db.commit()
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/scenarios/test_note_hashing.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add src/wizard/note_hashing.py src/wizard/tools/task_tools.py tests/scenarios/test_note_hashing.py
git commit -m "feat(notes): normalized content-hash helper for dedup"
```

---

### Task 2: Suppress the auto-closed boilerplate note

**Files:**
- Modify: `src/wizard/services.py` (`SessionCloser`, ~`:296-311`)
- Test: `tests/scenarios/test_session_closer_no_boilerplate_note.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `SessionCloser` no longer persists a `Note` when the summary is synthetic; `session.summary` is still set. `ClosedSessionSummary` return is unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/scenarios/test_session_closer_no_boilerplate_note.py`. Model the DB/session setup on the existing `SessionCloser` tests — search first: `ls tests/scenarios/ | grep -i clos` and copy that file's fixture/setup style. The assertion:

```python
# After SessionCloser closes an abandoned session that has a *synthetic* summary:
#   - session.summary is set (starts with "Auto-closed:")
#   - NO Note row exists for that session_id with content starting "Auto-closed:"
# Use the same construction the existing SessionCloser test uses to build the
# closer + an abandoned session with no user summary, then assert:
notes = db.execute(
    select(Note).where(Note.session_id == session_id)
).scalars().all()
assert all(not n.content.startswith("Auto-closed:") for n in notes)
assert session.summary.startswith("Auto-closed:")
```

If no existing SessionCloser test exists to model, build the fixture: create a `WizardSession` (agent='claude-code'), flush, then call the `SessionCloser`'s close method the same way `session_start` does (`close_recent_abandoned`), using the `security`/repo fixtures from conftest.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scenarios/test_session_closer_no_boilerplate_note.py -v`
Expected: FAIL — a Note with content starting `"Auto-closed:"` currently exists.

- [ ] **Step 3: Make the change**

In `src/wizard/services.py`, locate the block (around `:296-311`):

```python
        summary_text, closed_via = self._synthetic_summary(session, notes, task_ids)
        clean_summary = self._security.scrub(summary_text).clean
        session.summary = clean_summary
        session.session_state = state.model_dump_json()
        if session.closed_by is None:
            session.closed_by = "auto"
        db.add(session)
        db.flush()
        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content=clean_summary,
            session_id=session_id,
            artifact_id=session.artifact_id,
            artifact_type="session",
        )
        self._note_repo.save(db, note)
```

Guard the note write on non-synthetic summaries:

```python
        summary_text, closed_via = self._synthetic_summary(session, notes, task_ids)
        clean_summary = self._security.scrub(summary_text).clean
        session.summary = clean_summary
        session.session_state = state.model_dump_json()
        if session.closed_by is None:
            session.closed_by = "auto"
        db.add(session)
        db.flush()
        # Skip the SESSION_SUMMARY note for synthetic (interrupted-session)
        # summaries — it is pure boilerplate ("Auto-closed: …"). The session
        # row records closure; no memory-worthy note exists here.
        if closed_via != "synthetic":
            note = Note(
                note_type=NoteType.SESSION_SUMMARY,
                content=clean_summary,
                session_id=session_id,
                artifact_id=session.artifact_id,
                artifact_type="session",
            )
            self._note_repo.save(db, note)
```

- [ ] **Step 4: Run test + regression**

Run: `uv run pytest tests/scenarios/test_session_closer_no_boilerplate_note.py -v`
Expected: PASS.
Run: `uv run pytest tests/scenarios/ -k "session" -q`
Expected: PASS (no session/closer test regressed).

- [ ] **Step 5: Commit**

```bash
git add src/wizard/services.py tests/scenarios/test_session_closer_no_boilerplate_note.py
git commit -m "feat(notes): stop persisting auto-closed boilerplate as a note"
```

---

### Task 3: Harden the OBSERVATION firehose (scrub + hash + dedup)

**Files:**
- Modify: `src/wizard/cli/hooks.py`
- Test: `tests/scenarios/test_stop_hook.py` (extend; create if absent)

**Interfaces:**
- Consumes: `note_hashing.content_hash` (Task 1); `deps.get_security`.
- Produces: `run_stop_hook` writes PII-scrubbed content, a normalized `content_hash`, and skips a write that duplicates an existing active note for the task.

- [ ] **Step 1: Write the failing tests**

Extend (or create) `tests/scenarios/test_stop_hook.py`. Model setup on the existing file if present (`ls tests/scenarios/ | grep -i stop`). Tests to add — they call `run_stop_hook(agent_session_id, message)` after seeding: a task + TaskState, a prior note for the session (so `_resolve_active_task_id` returns the task), and the keyed session dir `settings.paths.sessions_dir / <agent_session_id> / wizard_id` containing the wizard session id.

```python
def test_observation_is_pii_scrubbed(...):
    # message contains an email/name the scrubber redacts;
    # after run_stop_hook, the newest OBSERVATION note's content != raw message
    # and does not contain the raw PII token.

def test_observation_sets_content_hash(...):
    # after run_stop_hook, the OBSERVATION note.content_hash == content_hash(scrubbed_content)

def test_observation_dedups_verbatim_repeat(...):
    # call run_stop_hook twice with the same message;
    # only ONE OBSERVATION note for that task+hash exists.
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scenarios/test_stop_hook.py -v`
Expected: FAIL (content unscrubbed / content_hash NULL / duplicate written).

- [ ] **Step 3: Implement**

In `src/wizard/cli/hooks.py`, add imports:

```python
from ..deps import get_security
from ..note_hashing import content_hash as compute_content_hash
```

Change `run_stop_hook` to scrub and hash before writing, and pass the hash through. Replace the write call:

```python
        _write_observation(
            db_path, task_id, wizard_session_id, last_message[:NOTE_CONTENT_MAX_CHARS]
        )
```
with:
```python
        sec = get_security()
        clean = sec.scrub(last_message[:NOTE_CONTENT_MAX_CHARS]).clean
        c_hash = compute_content_hash(clean)
        _write_observation(db_path, task_id, wizard_session_id, clean, c_hash)
```

Change `_write_observation` to accept the hash, dedup on it, and store it:

```python
def _write_observation(
    db_path: Path, task_id: int, session_id: int, content: str, content_hash: str
) -> None:
    """Insert OBSERVATION note (deduped, hashed) and update task_state counts."""
    now = datetime.now().isoformat()
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            dup = conn.execute(
                "SELECT 1 FROM note"
                " WHERE task_id = ? AND content_hash = ? AND status = 'active' LIMIT 1",
                (task_id, content_hash),
            ).fetchone()
            if dup is not None:
                return
            conn.execute(
                "INSERT INTO note"
                " (note_type, content, content_hash, task_id, session_id, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (NoteType.OBSERVATION.value, content, content_hash, task_id, session_id, now, now),
            )
            conn.execute(
                """
                UPDATE task_state
                SET note_count = COALESCE(note_count, 0) + 1,
                    observation_count = COALESCE(observation_count, 0) + 1,
                    last_note_at = ?,
                    last_touched_at = ?,
                    stale_days = 0
                WHERE task_id = ?
                """,
                (now, now, task_id),
            )
            conn.commit()
    except Exception as e:
        logger.debug("hook: failed to write observation: %s", e)
```

- [ ] **Step 4: Run tests + regression**

Run: `uv run pytest tests/scenarios/test_stop_hook.py -v`
Expected: PASS.
Run: `uv run pytest tests/scenarios/ -k "hook or note" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/wizard/cli/hooks.py tests/scenarios/test_stop_hook.py
git commit -m "feat(notes): scrub, hash, and dedup Stop-hook observations"
```

---

### Task 4: Read-side `active_only` filters on the note repository

**Files:**
- Modify: `src/wizard/repositories/note.py` (`get_for_task`, `get_notes_grouped_by_task`)
- Modify callers: `src/wizard/tools/task_tools.py` (`_select_key_notes` ~`:147,153`), `src/wizard/tools/query_tools.py` (`get_task` ~`:132`), `src/wizard/tools/session_tools.py` (`_group_prior_notes`)
- Test: `tests/scenarios/test_active_only_recall.py` (create)

**Interfaces:**
- Produces: `get_for_task(db, task_id, ascending=False, limit=None, active_only=False)`; `get_notes_grouped_by_task(db, session_id, active_only=False)`. When `active_only=True`, only `status == 'active'` notes are returned. `rewind_task` continues to call with the default (`active_only=False`).

- [ ] **Step 1: Write the failing test**

Create `tests/scenarios/test_active_only_recall.py`:

```python
from sqlalchemy.orm import Session as SASession
from sqlalchemy import text

from wizard.database import engine
from wizard.models import Note, NoteType, Task, TaskState
from wizard.repositories.note import NoteRepository


def test_get_for_task_active_only_excludes_demoted():
    repo = NoteRepository()
    with SASession(engine) as db:
        t = Task(name="active-only-task"); db.add(t); db.flush()
        db.add(TaskState(task_id=t.id)); db.flush()
        a = Note(note_type=NoteType.DECISION, content="live decision", task_id=t.id,
                 status="active", artifact_id=f"t{t.id}", artifact_type="task")
        s = Note(note_type=NoteType.DECISION, content="stale decision", task_id=t.id,
                 status="superseded", artifact_id=f"t{t.id}", artifact_type="task")
        db.add(a); db.add(s); db.commit()
        try:
            all_notes = repo.get_for_task(db, t.id)                     # default False
            active = repo.get_for_task(db, t.id, active_only=True)
            all_ids = {n.id for n in all_notes}
            active_ids = {n.id for n in active}
            assert a.id in all_ids and s.id in all_ids                  # history sees both
            assert a.id in active_ids and s.id not in active_ids        # recall excludes demoted
        finally:
            db.delete(a); db.delete(s)
            db.execute(text("DELETE FROM task_state WHERE task_id=:i"), {"i": t.id})
            db.delete(t); db.commit()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scenarios/test_active_only_recall.py -v`
Expected: FAIL — `get_for_task() got an unexpected keyword argument 'active_only'`.

- [ ] **Step 3: Add the params**

In `src/wizard/repositories/note.py`, change `get_for_task`:

```python
    def get_for_task(
        self,
        db: Session,
        task_id: int | None,
        ascending: bool = False,
        limit: int | None = None,
        active_only: bool = False,
    ) -> list[Note]:
        if task_id is None:
            return []
        order = col(Note.created_at).asc() if ascending else col(Note.created_at).desc()
        stmt = select(Note).where(Note.task_id == task_id)
        if active_only:
            stmt = stmt.where(Note.status == "active")
        stmt = stmt.order_by(order)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(db.exec(stmt).all())
```

And `get_notes_grouped_by_task`:

```python
    def get_notes_grouped_by_task(
        self, db: Session, session_id: int, active_only: bool = False
    ) -> dict[int, list[Note]]:
        """Return notes for a session grouped by task_id, ordered by created_at asc."""
        stmt = select(Note).where(Note.session_id == session_id)
        if active_only:
            stmt = stmt.where(Note.status == "active")
        stmt = stmt.order_by(col(Note.created_at).asc())
        all_notes = list(db.exec(stmt).all())
        by_task: dict[int, list[Note]] = {}
        for n in all_notes:
            if n.task_id is not None:
                by_task.setdefault(n.task_id, []).append(n)
        return by_task
```

- [ ] **Step 4: Update recall callers to pass `active_only=True`**

- `src/wizard/tools/task_tools.py` — in `_select_key_notes` (the `get_for_task` call(s) around `:147,153`), add `active_only=True` to each `n_repo.get_for_task(...)` call used to build task_start context.
- `src/wizard/tools/query_tools.py` — `get_task`'s `get_for_task(...)` call (~`:132`): add `active_only=True`.
- `src/wizard/tools/session_tools.py` — `_group_prior_notes` (resume): its `get_notes_grouped_by_task(...)` call: add `active_only=True`.
- Do NOT change `rewind_task` (`tools/note_tools.py:41`) — it must keep the default `active_only=False` (full history).

- [ ] **Step 5: Run test + regression**

Run: `uv run pytest tests/scenarios/test_active_only_recall.py -v`
Expected: PASS.
Run: `uv run pytest tests/scenarios/ -k "task_start or rewind or resume or query or get_task" -q`
Expected: PASS (all existing notes are `active`, so passing `True` changes nothing for them).

- [ ] **Step 6: Commit**

```bash
git add src/wizard/repositories/note.py src/wizard/tools/task_tools.py src/wizard/tools/query_tools.py src/wizard/tools/session_tools.py tests/scenarios/test_active_only_recall.py
git commit -m "feat(recall): opt-in active_only note filters (exclude demoted from recall)"
```

---

### Task 5: Exclude demoted notes from search

**Files:**
- Modify: `src/wizard/repositories/search.py` (`_search_notes` metadata fetch, ~`:136-140`)
- Test: `tests/scenarios/test_search_excludes_demoted.py` (create)

**Interfaces:**
- Consumes: `SearchRepository.hybrid_search` (unchanged signature).
- Produces: a note with `status != 'active'` never appears in search results even if its FTS row matches.

- [ ] **Step 1: Write the failing test**

Create `tests/scenarios/test_search_excludes_demoted.py`:

```python
from sqlalchemy.orm import Session as SASession
from sqlalchemy import text

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories.search import SearchRepository


def test_demoted_note_excluded_from_search():
    repo = SearchRepository()
    with SASession(engine) as db:
        n = Note(note_type=NoteType.DECISION,
                 content="quokka migration blueprint alpha", task_id=None,
                 status="superseded", artifact_id="demoted-1", artifact_type="note")
        db.add(n); db.commit()
        try:
            res = repo.hybrid_search(db, "quokka migration blueprint", limit=10)
            assert all(r.entity_id != n.id for r in res if r.entity_type == "note")
        finally:
            db.delete(n); db.commit()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scenarios/test_search_excludes_demoted.py -v`
Expected: FAIL — the superseded note is returned (search ignores status today).

- [ ] **Step 3: Add the status filter to the metadata fetch**

In `src/wizard/repositories/search.py`, the note metadata query in `_search_notes` currently reads:

```python
            "SELECT id AS entity_id, content, note_type, task_id, created_at "
            "FROM note WHERE id IN :ids"
```
Change the WHERE clause to exclude non-active notes:
```python
            "SELECT id AS entity_id, content, note_type, task_id, created_at "
            "FROM note WHERE id IN :ids AND status = 'active'"
```

Because the lane id lists are filtered to `if i in meta` when building `bm25_lane`/`vec_lane`, a demoted note dropped from `meta` is automatically dropped from both lanes and from `results`.

- [ ] **Step 4: Run test + full search regression**

Run: `uv run pytest tests/scenarios/test_search_excludes_demoted.py -v`
Expected: PASS.
Run: `uv run pytest tests/scenarios/test_search_engine.py tests/scenarios/test_search.py tests/scenarios/test_fts_stemming.py tests/eval/test_search_recall_benchmark.py -q`
Expected: PASS (all seeded notes are `active`).

- [ ] **Step 5: Commit**

```bash
git add src/wizard/repositories/search.py tests/scenarios/test_search_excludes_demoted.py
git commit -m "feat(search): exclude non-active notes from results"
```

---

### Task 6: `mark_note` MCP tool

**Files:**
- Add: `src/wizard/schemas.py` (`MarkNoteResponse`)
- Add: `src/wizard/repositories/note.py` (`set_status`)
- Add: `src/wizard/tools/note_tools.py` (`mark_note` + registration)
- Modify: `src/wizard/tools/__init__.py` (import/register/export)
- Test: `tests/scenarios/test_mark_note.py` (create)

**Interfaces:**
- Consumes: `get_note_repo`, `get_session`.
- Produces: `mark_note(note_id: int, status: str, superseded_by_note_id: int | None = None) -> MarkNoteResponse`. `MarkNoteResponse(note_id: int, status: str, superseded_by_note_id: int | None)`. `NoteRepository.set_status(db, note_id, status, superseded_by_note_id=None) -> Note`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scenarios/test_mark_note.py`:

```python
import pytest
from sqlalchemy.orm import Session as SASession
from sqlalchemy import text
from fastmcp.exceptions import ToolError

from wizard.database import engine, get_session
from wizard.models import Note, NoteType
from wizard.repositories.note import NoteRepository


def _mk_note(db, content, status="active"):
    n = Note(note_type=NoteType.INVESTIGATION, content=content, task_id=None,
             status=status, artifact_id=f"mn-{content}", artifact_type="note")
    db.add(n); db.flush()
    return n


def test_set_status_demotes_and_links():
    repo = NoteRepository()
    with SASession(engine) as db:
        old = _mk_note(db, "old finding"); new = _mk_note(db, "new finding")
        db.commit()
        try:
            repo.set_status(db, old.id, "superseded", superseded_by_note_id=new.id)
            db.commit()
            db.refresh(old); db.refresh(new)
            assert old.status == "superseded"
            assert new.supersedes_note_id == old.id
        finally:
            db.delete(old); db.delete(new); db.commit()


def test_set_status_reversible():
    repo = NoteRepository()
    with SASession(engine) as db:
        n = _mk_note(db, "toggle", status="superseded"); db.commit()
        try:
            repo.set_status(db, n.id, "active"); db.commit(); db.refresh(n)
            assert n.status == "active"
        finally:
            db.delete(n); db.commit()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scenarios/test_mark_note.py -v`
Expected: FAIL — `NoteRepository` has no `set_status`.

- [ ] **Step 3: Add `set_status` to the repository**

In `src/wizard/repositories/note.py`:

```python
    def set_status(
        self, db: Session, note_id: int, status: str,
        superseded_by_note_id: int | None = None,
    ) -> Note:
        note = db.get(Note, note_id)
        if note is None:
            raise ValueError(f"Note {note_id} not found")
        note.status = status
        db.add(note)
        if superseded_by_note_id is not None:
            winner = db.get(Note, superseded_by_note_id)
            if winner is None:
                raise ValueError(f"Note {superseded_by_note_id} not found")
            winner.supersedes_note_id = note_id
            db.add(winner)
        elif status == "active":
            # clearing a demotion: drop any back-link that pointed at this note
            for w in db.exec(select(Note).where(Note.supersedes_note_id == note_id)).all():
                w.supersedes_note_id = None
                db.add(w)
        db.flush()
        return note
```

Ensure `select` is imported at the top of `note.py` (it already is — `from sqlmodel import ... select`).

- [ ] **Step 4: Run the repo tests**

Run: `uv run pytest tests/scenarios/test_mark_note.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Add `MarkNoteResponse` schema**

In `src/wizard/schemas.py`, near `SaveNoteResponse`:

```python
class MarkNoteResponse(BaseModel):
    note_id: int
    status: str
    superseded_by_note_id: int | None = None
```

- [ ] **Step 6: Add the `mark_note` tool + register it**

In `src/wizard/tools/note_tools.py`: add `MarkNoteResponse` to the `..schemas` import list; add `NoteStatus` to a `..models` import; then add the tool and its registration.

```python
from ..models import NoteStatus  # add to existing model imports

_MARKABLE = {s.value for s in NoteStatus}


async def mark_note(
    note_id: int,
    status: str,
    superseded_by_note_id: int | None = None,
    n_repo: NoteRepository = Depends(get_note_repo),
) -> MarkNoteResponse:
    """Deliberately set a note's status (e.g. supersede/invalidate a stale note).

    `active` is the only recall-eligible status; any other value hides the note
    from recall (task_start, get_task, resume, search) while rewind_task still
    shows it. Pass `superseded_by_note_id` (only with status='superseded') to
    record that a newer note replaced this one.
    """
    status = status.lower()
    if status not in _MARKABLE:
        raise ToolError(f"invalid status {status!r}; must be one of {sorted(_MARKABLE)}")
    if superseded_by_note_id is not None and status != "superseded":
        raise ToolError("superseded_by_note_id is only valid with status='superseded'")
    with get_session() as db:
        try:
            note = n_repo.set_status(db, note_id, status, superseded_by_note_id)
        except ValueError as e:
            raise ToolError(str(e)) from e
        return MarkNoteResponse(
            note_id=note.id,  # type: ignore[arg-type]
            status=note.status,
            superseded_by_note_id=superseded_by_note_id,
        )


mcp.tool()(mark_note)
```

In `src/wizard/tools/__init__.py`: add `mark_note` to the `from .note_tools import ...` line and to the `__all__` list.

- [ ] **Step 7: Add tool-level + end-to-end tests**

Append to `tests/scenarios/test_mark_note.py`:

```python
async def test_mark_note_rejects_bad_status():
    from wizard.tools.note_tools import mark_note
    from wizard.repositories.note import NoteRepository
    with SASession(engine) as db:
        n = _mk_note(db, "bad-status"); db.commit()
    try:
        with pytest.raises(ToolError):
            await mark_note(n.id, "bogus", n_repo=NoteRepository())
        with pytest.raises(ToolError):
            await mark_note(n.id, "active", superseded_by_note_id=n.id, n_repo=NoteRepository())
    finally:
        with SASession(engine) as db:
            db.delete(db.get(Note, n.id)); db.commit()


def test_demote_hides_note_from_search():
    from wizard.repositories.search import SearchRepository
    repo = NoteRepository(); search = SearchRepository()
    with SASession(engine) as db:
        n = _mk_note(db, "wombat telemetry pipeline zeta"); db.commit()
        try:
            before = search.hybrid_search(db, "wombat telemetry pipeline", limit=10)
            assert any(r.entity_id == n.id for r in before if r.entity_type == "note")
            repo.set_status(db, n.id, "superseded"); db.commit()
            after = search.hybrid_search(db, "wombat telemetry pipeline", limit=10)
            assert all(r.entity_id != n.id for r in after if r.entity_type == "note")
        finally:
            db.delete(db.get(Note, n.id)); db.commit()
```

Note: `test_mark_note_rejects_bad_status` is async — this repo's pytest is configured for async tests (see other `async def test_` scenarios). If a plain `async def` test is not auto-collected, add `@pytest.mark.anyio` matching the sibling async tests' decorator.

- [ ] **Step 8: Run tests + regression**

Run: `uv run pytest tests/scenarios/test_mark_note.py -v`
Expected: PASS.
Run: `uv run pytest tests/scenarios/ -k "note or search or tool" -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/wizard/schemas.py src/wizard/repositories/note.py src/wizard/tools/note_tools.py src/wizard/tools/__init__.py tests/scenarios/test_mark_note.py
git commit -m "feat(notes): add mark_note tool for deliberate note demotion"
```

---

### Task 7: Teach the note skill to use `mark_note`

**Files:**
- Modify: the note skill under `src/wizard/skills/` (locate: `ls src/wizard/skills/` then find the note skill file/dir)

**Interfaces:** none (documentation).

- [ ] **Step 1: Locate the note skill**

Run: `ls -R src/wizard/skills/ | grep -i note`
Identify the note skill markdown (e.g. `src/wizard/skills/note/SKILL.md` or `src/wizard/skills/note.md`).

- [ ] **Step 2: Add a "Demoting stale notes" section**

Append a short section to that skill file:

```markdown
## Demoting stale or wrong notes

When a new finding **supersedes or contradicts** a note you already saved, don't
leave both to compete in recall — demote the old one with `mark_note`:

- `mark_note(note_id=<old>, status="superseded", superseded_by_note_id=<new>)` —
  the old note is hidden from recall (task_start, get_task, resume, search) and
  the new note records that it replaced it. `rewind_task` still shows the old note.
- `mark_note(note_id=<id>, status="contradicted" | "invalid")` — for a note later
  found wrong, with no single replacement.
- `mark_note(note_id=<id>, status="active")` — reverse a demotion.

`active` is the only status that surfaces in recall. Demote deliberately; when in
doubt, leave the note active.
```

- [ ] **Step 3: Verify the skill still parses / no broken frontmatter**

Run: `uv run python -c "import pathlib; print('ok' if pathlib.Path('<the skill file path>').read_text().count('---') >= 2 else 'check frontmatter')"`
Expected: `ok` (frontmatter intact).

- [ ] **Step 4: Commit**

```bash
git add src/wizard/skills/
git commit -m "docs(skill): teach the note skill to demote stale notes with mark_note"
```

---

### Task 8: Noise-audit script

**Files:**
- Create: `scripts/audit_note_quality.py`

**Interfaces:** none (read-only CLI).

- [ ] **Step 1: Write the script**

Create `scripts/audit_note_quality.py`:

```python
"""Read-only note corpus-health audit against the real ~/.wizard/wizard.db.

Not part of CI. Run before/after Phase 2 to see the noise drop:
    uv run python scripts/audit_note_quality.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text

DB = Path.home() / ".wizard" / "wizard.db"


def main() -> int:
    if not DB.exists():
        print(f"No DB at {DB}; nothing to audit.")
        return 0
    engine = create_engine(f"sqlite:///{DB}?mode=ro", connect_args={"uri": True})
    with engine.connect() as c:
        total = c.execute(text("SELECT count(*) FROM note")).scalar() or 0
        by_type = c.execute(text(
            "SELECT note_type, count(*) FROM note GROUP BY note_type")).all()
        by_status = c.execute(text(
            "SELECT status, count(*) FROM note GROUP BY status")).all()
        boilerplate = c.execute(text(
            "SELECT count(*) FROM note WHERE content LIKE 'Auto-closed:%'")).scalar() or 0
        anchored = c.execute(text(
            "SELECT count(*) FROM note WHERE task_id IS NOT NULL")).scalar() or 0
        exact_dups = c.execute(text(
            "SELECT count(*) FROM (SELECT content FROM note GROUP BY content HAVING count(*)>1)"
        )).scalar() or 0
        null_hash = c.execute(text(
            "SELECT count(*) FROM note WHERE content_hash IS NULL")).scalar() or 0

    pct = lambda n: f"{(100 * n / total):.0f}%" if total else "0%"
    print(f"notes: {total}")
    print(f"  by type:   " + ", ".join(f"{t}={n}" for t, n in by_type))
    print(f"  by status: " + ", ".join(f"{s}={n}" for s, n in by_status))
    print(f"  boilerplate (Auto-closed:): {boilerplate} ({pct(boilerplate)})")
    print(f"  task-anchored: {anchored} ({pct(anchored)})")
    print(f"  exact-duplicate content groups: {exact_dups}")
    print(f"  null content_hash (un-deduped): {null_hash}")
    demoted = sum(n for s, n in by_status if s != "active")
    print(f"  demoted (non-active): {demoted} ({pct(demoted)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the real DB**

Run: `uv run python scripts/audit_note_quality.py`
Expected: prints the corpus-health report without error (read-only; content depends on the live DB).

- [ ] **Step 3: Commit**

```bash
git add scripts/audit_note_quality.py
git commit -m "chore(notes): add read-only note-quality audit script"
```

---

## Final verification

- [ ] `uv run pytest -q` → all pass.
- [ ] `uv run python scripts/audit_note_quality.py` → runs, shows boilerplate/demoted counts.

---

## Self-Review notes (author)

- **Spec coverage:** 2a-1 → Task 2; 2a-2 → Task 3; 2a-3 → Task 1; 2b-1 read filters → Tasks 4 (repo) + 5 (search); 2b-2 `mark_note` → Task 6; 2b-3 note-skill → Task 7; Stage 3 tests → embedded in Tasks 2–6; Stage 3 audit script → Task 8. All covered.
- **Deferred (no task — correct):** LLM auto-supersession, cross-task/semantic dedup, `reference_count` decay, synthesis rebuild.
- **Type consistency:** `active_only: bool = False` identical across `get_for_task`/`get_notes_grouped_by_task` (Task 4) and honoured by callers; `set_status(db, note_id, status, superseded_by_note_id=None)` (Task 6 repo) matches the `mark_note(note_id, status, superseded_by_note_id=None)` tool and `MarkNoteResponse` fields; `content_hash`/`normalize_for_hash` names identical in Tasks 1 and 3.
- **Non-breaking:** every `active_only` defaults `False`; the search filter and read filters are no-ops while all notes are `active` (true of the whole existing corpus), so existing tests stay green.
