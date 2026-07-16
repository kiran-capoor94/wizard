# Adoption Ergonomics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make wizard adoption automatic and low-friction — the `SessionStart` hook injects a real memory brief every session (no ritual), and saving a note becomes a single call.

**Architecture:** A testable read-only `render_brief(db)` / `build_session_brief(db_path)` in `src/wizard/session_brief.py`, exposed via a `wizard hook session-brief` CLI, invoked by `session-start.sh` and injected as `additionalContext`. Plus a docs-only rewrite of the note skill to lead with a one-call fast path. No migration, no `save_note` code change.

**Tech Stack:** Python 3.13, SQLModel/SQLAlchemy, SQLite, Typer CLI, pytest, uv, bash hooks.

## Global Constraints

- **Read-only:** `build_session_brief` opens `db_path` with `sqlite:///…?mode=ro` (`connect_args={"uri": True}`) — never read-write (avoid lock contention with the running server). It must never raise into the hook — return `""` on any error/empty DB.
- **Reuse existing scoring/queries** (DRY, ordering parity with `session_start`): `TaskRepository.count_open_tasks`, `get_open_task_index(limit=…)`, `get_blocked_task_index`, and `SessionRepository.get_prior_summaries(db, current_session_id)`. Do NOT re-implement the task score.
- **Token budget:** the brief is injected into every session — hard cap `_BRIEF_MAX_LINES = 25`, summary truncated to `_SUMMARY_MAX_CHARS = 160`.
- **No silent `note_type` default** in the fast-path skill or the tool — `note_type` stays explicit (silently defaulting to `INVESTIGATION` re-introduces the Phase-2 mistyped-note pollution).
- Tests run with `uv run pytest`. FTS/DB-dependent tests use the migrated process-wide engine (`from wizard.database import engine`); the shared engine is process-wide — any test seeding it cleans up in `try/finally`.
- **Ruff clean** (repo enforces E702/I001): run `uv run ruff check --fix` on changed files and confirm clean before each commit.
- **DB safety:** never run ad-hoc `python -c` importing `wizard.database` without `WIZARD_CONFIG_FILE` set — use `uv run pytest`.
- Commit after each task; `git add` only the files that task changed (never `git add -A`/`uv.lock`).

---

## File Structure

- `src/wizard/session_brief.py` — **new**. `render_brief(db: Session) -> str` (core, testable) + `build_session_brief(db_path: str) -> str` (read-only wrapper).
- `src/wizard/cli/main.py` — **modify**. Add `@hook_app.command("session-brief")`.
- `src/wizard/hooks/session-start.sh` — **modify**. Step 2 calls `wizard hook session-brief` and injects it.
- `src/wizard/skills/note/SKILL.md` — **modify**. Lead with the one-call fast path; move ceremony to an appendix.
- `tests/scenarios/test_session_brief.py` — **new**.

---

### Task 1: `session_brief` module + `wizard hook session-brief` CLI

**Files:**
- Create: `src/wizard/session_brief.py`
- Modify: `src/wizard/cli/main.py` (add hook subcommand)
- Test: `tests/scenarios/test_session_brief.py` (create)

**Interfaces:**
- Consumes: `TaskRepository.count_open_tasks(db)`, `get_open_task_index(db, limit)` → `list[TaskIndexEntry]` (fields: `id, name, status, priority, note_count, notes_by_type, last_note_hint, last_worked_at, stale_days`), `get_blocked_task_index(db, limit=None)` → list; `SessionRepository.get_prior_summaries(db, current_session_id)` → `list[PriorSessionSummary]` (field `.summary`). `TaskStatus` from `..models`.
- Produces: `render_brief(db: Session) -> str`; `build_session_brief(db_path: str) -> str`. CLI: `wizard hook session-brief` prints the brief.

- [ ] **Step 1: Write the failing tests**

Create `tests/scenarios/test_session_brief.py`:

```python
from sqlalchemy import text
from sqlmodel import Session as SASession, SQLModel, create_engine

from wizard.database import engine
from wizard.models import Note, NoteType, Task, TaskState, TaskStatus, WizardSession
from wizard.repositories import TaskRepository
from wizard.session_brief import build_session_brief, render_brief


def test_render_brief_empty_db_returns_empty():
    # A DB with no open tasks / blocked / summaries → "".
    # Use a throwaway in-memory engine with just the ORM tables.
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    with SASession(eng) as db:
        assert render_brief(db) == ""


def test_render_brief_lists_open_tasks_and_summary():
    with SASession(engine) as db:
        t1 = Task(name="brief-alpha in progress", status=TaskStatus.IN_PROGRESS)
        t2 = Task(name="brief-beta todo", status=TaskStatus.TODO)
        db.add(t1); db.add(t2); db.flush()
        db.add(TaskState(task_id=t1.id)); db.add(TaskState(task_id=t2.id))
        sess = WizardSession(agent="claude-code", summary="brief-prior-summary marker")
        db.add(sess); db.commit()
        try:
            brief = render_brief(db)
            assert "brief-alpha in progress" in brief
            assert "brief-beta todo" in brief
            assert "brief-prior-summary marker" in brief
            assert brief.count("\n") + 1 <= 25          # cap
            # ordering parity: task lines follow get_open_task_index order
            idx = TaskRepository().get_open_task_index(db, limit=5)
            ordered_ids = [e.id for e in idx if e.name.startswith("brief-")]
            positions = [brief.find(f"#{i} ") for i in ordered_ids]
            assert positions == sorted(positions)
        finally:
            db.execute(text("DELETE FROM task_state WHERE task_id IN (:a,:b)"), {"a": t1.id, "b": t2.id})
            db.delete(t1); db.delete(t2); db.delete(sess); db.commit()


def test_build_session_brief_readonly_path(tmp_path):
    db_file = tmp_path / "brief.db"
    eng = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(eng)
    with SASession(eng) as db:
        t = Task(name="brief-file-task", status=TaskStatus.TODO); db.add(t); db.flush()
        db.add(TaskState(task_id=t.id)); db.commit()
    eng.dispose()
    out = build_session_brief(str(db_file))
    assert "brief-file-task" in out


def test_build_session_brief_missing_db_returns_empty(tmp_path):
    assert build_session_brief(str(tmp_path / "nope.db")) == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scenarios/test_session_brief.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wizard.session_brief'`.

- [ ] **Step 3: Create the module**

Create `src/wizard/session_brief.py`:

```python
"""Compact, read-only session brief for proactive recall injection (SessionStart hook)."""
from __future__ import annotations

from sqlmodel import Session, create_engine

from .models import TaskStatus
from .repositories import SessionRepository, TaskRepository

_BRIEF_MAX_LINES = 25
_SUMMARY_MAX_CHARS = 160
_TOP_TASKS = 5


def render_brief(db: Session) -> str:
    """Render a compact memory brief from an open DB session. '' when nothing to show."""
    t_repo = TaskRepository()
    s_repo = SessionRepository()

    open_total = t_repo.count_open_tasks(db)
    open_index = t_repo.get_open_task_index(db, limit=_TOP_TASKS)
    blocked = t_repo.get_blocked_task_index(db)
    # No live session exists yet at SessionStart-hook time; pass -1 so nothing is excluded.
    summaries = s_repo.get_prior_summaries(db, current_session_id=-1)

    if open_total == 0 and not blocked and not summaries:
        return ""

    lines: list[str] = [
        f"[wizard memory] {open_total} open task(s), {len(blocked)} blocked."
    ]
    for e in open_index:
        tag = "in-progress" if e.status == TaskStatus.IN_PROGRESS else f"stale {e.stale_days}d"
        lines.append(f"  - #{e.id} {e.name} ({tag})")
    if summaries:
        summary = summaries[0].summary.replace("\n", " ").strip()[:_SUMMARY_MAX_CHARS]
        lines.append(f"Last session: {summary}")

    return "\n".join(lines[:_BRIEF_MAX_LINES])


def build_session_brief(db_path: str) -> str:
    """Open db_path READ-ONLY and render the brief. Returns '' on any error/empty DB.

    Never raises — this feeds a hook that must not interrupt the agent.
    """
    try:
        engine = create_engine(
            f"sqlite:///{db_path}?mode=ro", connect_args={"uri": True}
        )
        with Session(engine) as db:
            return render_brief(db)
    except Exception:
        return ""
```

- [ ] **Step 4: Run tests to verify module passes**

Run: `uv run pytest tests/scenarios/test_session_brief.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Add the CLI subcommand**

In `src/wizard/cli/main.py`, add after the existing `@hook_app.command("stop")` block:

```python
@hook_app.command("session-brief")
def hook_session_brief() -> None:
    """Print a compact read-only memory brief for the SessionStart hook."""
    from wizard.config import settings
    from wizard.session_brief import build_session_brief

    try:
        brief = build_session_brief(settings.db)
    except Exception:
        brief = ""
    if brief:
        typer.echo(brief)
```

(`typer` and `settings` import styles: match the file — `typer` is already imported at module top; import `settings`/`build_session_brief` locally inside the function to keep hook startup cheap, as other hook handlers do.)

- [ ] **Step 6: CLI smoke test**

Append to `tests/scenarios/test_session_brief.py`:

```python
def test_cli_session_brief_smoke(monkeypatch):
    from typer.testing import CliRunner
    from wizard.cli.main import app

    # settings is frozen, so don't patch settings.db. hook_session_brief does a
    # local `from wizard.session_brief import build_session_brief`, which re-reads
    # the name from that module at call time — so patch it there.
    monkeypatch.setattr(
        "wizard.session_brief.build_session_brief", lambda _p: "cli-brief-marker"
    )
    result = CliRunner().invoke(app, ["hook", "session-brief"])
    assert result.exit_code == 0
    assert "cli-brief-marker" in result.stdout
```

- [ ] **Step 7: Run tests + ruff**

Run: `uv run pytest tests/scenarios/test_session_brief.py -v`
Expected: PASS.
Run: `uv run ruff check --fix src/wizard/session_brief.py src/wizard/cli/main.py tests/scenarios/test_session_brief.py && uv run ruff check src/wizard/session_brief.py src/wizard/cli/main.py tests/scenarios/test_session_brief.py`
Expected: All checks passed.

- [ ] **Step 8: Commit**

```bash
git add src/wizard/session_brief.py src/wizard/cli/main.py tests/scenarios/test_session_brief.py
git commit -m "feat(recall): add session-brief builder + wizard hook session-brief CLI"
```

---

### Task 2: Inject the brief from `session-start.sh`

**Files:**
- Modify: `src/wizard/hooks/session-start.sh` (Step 2, the `CONTEXT`/injection block)

**Interfaces:**
- Consumes: `wizard hook session-brief` (Task 1) on PATH (the same way `stop.sh` calls `wizard hook stop`).

- [ ] **Step 1: Make the change**

In `src/wizard/hooks/session-start.sh`, the Step 2 block currently reads:

```bash
# ── Step 2: Session boot injection (always) ───────────────────────────────────
CONTEXT="Begin this session by calling the wizard:session_start MCP tool."
if [ -n "$AGENT_UUID" ]; then
    CONTEXT="agent_session_id=$AGENT_UUID source=$SOURCE. $CONTEXT"
fi

jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'
```

Replace it with (prepend the brief when present; keep the session_start instruction — `session_start` still creates the session row + `wizard_id` that capture depends on):

```bash
# ── Step 2: Session boot injection (always) ───────────────────────────────────
CONTEXT="Begin this session by calling the wizard:session_start MCP tool."
if [ -n "$AGENT_UUID" ]; then
    CONTEXT="agent_session_id=$AGENT_UUID source=$SOURCE. $CONTEXT"
fi

# Proactive recall: inject a compact read-only memory brief so orientation is
# automatic even before session_start is called. Never fatal.
BRIEF=$(wizard hook session-brief 2>/dev/null || true)
if [ -n "$BRIEF" ]; then
    CONTEXT="$BRIEF

$CONTEXT"
fi

jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx}}'
```

- [ ] **Step 2: Verify the script parses and the command works**

Run: `bash -n src/wizard/hooks/session-start.sh`
Expected: no output (syntax OK).
Run: `grep -n "wizard hook session-brief" src/wizard/hooks/session-start.sh`
Expected: the line is present.
Run (confirms the CLI the hook depends on emits without error against the real DB, read-only): `wizard hook session-brief; echo "exit=$?"`
Expected: prints the brief (or nothing on an empty DB) and `exit=0`.

Manual note (record in the report, not automated — hook→Claude injection isn't unit-testable): after deploy, a new session's injected context contains the brief block above the `session_start` instruction.

- [ ] **Step 3: Commit**

```bash
git add src/wizard/hooks/session-start.sh
git commit -m "feat(recall): inject session brief as SessionStart additionalContext"
```

---

### Task 3: Fast-path note skill (docs-only)

**Files:**
- Modify: `src/wizard/skills/note/SKILL.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Restructure the skill**

Preserve the existing frontmatter block verbatim (the `---` … `---` header, including `allowed-tools: mcp__wizard__save_note mcp__wizard__mark_note ToolSearch`). Immediately after the frontmatter and the `# Save Note` title, insert this new leading section:

```markdown
## Fast path (default)

Most saves are one call:

    save_note(content="<specific finding>", note_type="<type>", task_id=<current task id, or omit>)

- **content** must be specific — include a file path, function name, error, concrete finding, or explicit rationale. (Vague notes are the one thing worth slowing down for.)
- **note_type** — pick one, no ceremony: `investigation | decision | docs | learnings | failure | observation`. (Never guess-default it — an honest type keeps `what_am_i_missing` accurate.)
- **task_id** — pass the current task if you have one; omit to anchor to the session.
- `mental_model` is optional — add a 1–2 sentence snapshot when your understanding of the problem shifts.

That's it. Dedup + demotion (`mark_note`) keep the store clean, so saving cheaply is safe — save as you go rather than hoarding findings for a big write-up.

## Thorough mode (reference)

Use the material below when you want to be deliberate — the note-type decision tree, per-type templates, and anti-patterns. It is guidance, not a gate: never let it stop you from doing the one-call save above.
```

Then move the EXISTING body (the Hard Gates, Note Type Decision Tree, Content Templates, Mental Model, Steps, Anti-Patterns sections — everything that was after the title) so it now sits UNDER the new `## Thorough mode (reference)` heading (i.e., it becomes reference material, not the default flow). Do not rewrite that existing content — just relocate it beneath the new heading. Remove any now-duplicated "how to call save_note" scaffolding that the fast path already covers, but keep the templates and decision tree intact.

- [ ] **Step 2: Verify structure**

Run: `sed -n '1,8p' src/wizard/skills/note/SKILL.md`
Expected: the frontmatter block is intact (opening `---`, `name: note`, `allowed-tools:` including `mcp__wizard__mark_note`, closing `---`).
Run: `grep -nE "^## Fast path \(default\)|^## Thorough mode \(reference\)" src/wizard/skills/note/SKILL.md`
Expected: both headings present, "Fast path" appearing before "Thorough mode".
Run: `grep -c "Decision Tree\|Templates\|Anti-Patterns" src/wizard/skills/note/SKILL.md`
Expected: ≥ 1 (the existing reference material was relocated, not deleted).

- [ ] **Step 3: Commit**

```bash
git add src/wizard/skills/note/SKILL.md
git commit -m "docs(skill): lead the note skill with a one-call fast path"
```

---

## Final verification

- [ ] `uv run pytest -q` → all pass.
- [ ] `uv run ruff check src/wizard/session_brief.py src/wizard/cli/main.py tests/scenarios/test_session_brief.py` → clean.
- [ ] `wizard hook session-brief` prints a brief (or empty) and exits 0.
- [ ] `bash -n src/wizard/hooks/session-start.sh` clean; the brief call is wired into Step 2.

---

## Self-Review notes (author)

- **Spec coverage:** Section 1 brief-builder → Task 1 (`render_brief`/`build_session_brief`); CLI → Task 1; hook injection → Task 2; Section 2 fast-path skill → Task 3; Section 3 measurement → Task 1 unit tests (counts/ordering/summary/cap/empty) + CLI smoke, Task 2 CLI/`bash -n` checks, Task 3 structure grep. All covered.
- **Deferred (no task — correct):** Stop-hook nudge, ambient capture, synthesis rebuild.
- **Type consistency:** `render_brief(db: Session) -> str` and `build_session_brief(db_path: str) -> str` used identically across Tasks 1–2; `TaskIndexEntry` fields (`id`, `name`, `status`, `stale_days`) referenced match `schemas.py`; `get_prior_summaries(db, current_session_id=-1)` matches the repo signature; constants (`_BRIEF_MAX_LINES=25`, `_SUMMARY_MAX_CHARS=160`, `_TOP_TASKS=5`) defined once.
- **Read-only + no-raise:** `build_session_brief` opens `?mode=ro` and swallows all exceptions → `""`, so the hook can never break a session start.
- **Non-breaking:** additive hook injection (keeps the existing `session_start` instruction); no migration; no `save_note` tool change; skill change is docs-only.
