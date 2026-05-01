# Rulecheck — Wizard Rules Guide

Authoritative violation reference for the rulecheck subagent. Read in full before scanning.

---

## Tier Definitions

| Tier | Fix policy |
|------|-----------|
| **Tier 1** | Fix automatically — mechanical, low blast radius |
| **Tier 2** | Document only — requires design judgment |

---

## Violation Table

| Rule | CLAUDE.md ref | Tier | What to look for |
|------|--------------|------|-----------------|
| **SLAP** | Rule 1 | 2 | Tool functions building SQL strings, formatting API payloads, or doing multi-step transformation instead of delegating to a repo/service |
| **Unidirectional deps** | Rule 2 | 1 | `repositories/*.py` importing from `tools/`; integrations importing from services |
| **No N+1** | Rule 8 | 1 | `db.get()` or `session.exec()` inside a `for` loop body |
| **`_` prefix on public functions** | Rule 6 | 1 | `_`-prefixed function imported by another module |
| **No C901** | Rule 11 | 2 | Functions with cyclomatic complexity > 10 (ruff check --select C901 src/) |
| **File size cap** | File Size section | 1 | Any `src/wizard/**/*.py` or `tests/**/*.py` over 500 lines |
| **`ctx.sample()` discipline** | Rule 12 | 2 | `ctx.sample()` used for formatting, slug gen, or existence checks |

---

## Detection Commands

Run these from the repo root to find violations:

- Unidirectional dep violations: `grep -rn "from.*tools" src/wizard/repositories/`
- Underscore-prefix public imports: `grep -rn "import _" src/wizard/`
- File size violations: `find src/wizard tests -name "*.py" | xargs wc -l | awk '$1 > 500 && $2 != "total"'`
- C901 complexity: `ruff check --select C901 src/`
- N+1 rough scan: `grep -n "for .* in" src/wizard/tools/*.py src/wizard/repositories/*.py`

---

## Fix Guidance (Tier 1)

**Unidirectional deps:** Move the symbol to a lower layer both callers can import. Never add a tool import to a repo.

**No N+1:** Replace per-loop `.get()` with a single `.in_()` batch query before the loop; build a `{id: obj}` dict for O(1) lookup.

**`_` prefix on public functions:** Remove the `_` prefix from the definition; call sites importing it stay the same (they already import without the prefix — that was the violation signal).

**File size cap:** Split following CLAUDE.md structural split triggers (see docs/dev/architecture.md).

---

## Scope

Scan: `src/wizard/**/*.py`, `tests/**/*.py`

Do NOT scan: `alembic/`, `hooks/`, `scripts/`, `docs/`

---

## False Positive Guidance

| Situation | Not a violation |
|-----------|----------------|
| `_`-prefixed function never imported outside its module | Correct use — skip |
| `for` loop over 3 or fewer constant items with a repo call | Not meaningful N+1 — skip |
| `ctx.sample()` prompt requires genuine multi-step reasoning | Legitimate — skip |
