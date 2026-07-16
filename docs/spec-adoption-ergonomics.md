# Spec — Adoption Ergonomics (automatic recall + frictionless capture)

**Task:** unassigned (track in wizard once implementation starts)
**Status:** Approved design, ready to implement.
**Last updated:** 2026-07-16
**Scope:** Thread E, Phase 3 of 3 — first cut. Two deferred cuts (Stop-hook capture nudge, ambient no-LLM capture) are out of scope, gated as noted below.

---

## Problem Statement

Phases 1–2 fixed recall quality and note signal. The remaining failure is **adoption**: the memory layer gets skipped. All four adoption gaps bite — the human skips the session/task rituals; the agent skips `save_note` mid-work; the skills are heavy chores; and ideally none of it should require remembering. The root is the **manual/ritual model** itself.

Two facts from the code shape (and constrain) the fix:

1. **Recall is not actually automatic.** `session-start.sh` Step 2 injects only an instruction — `CONTEXT="Begin this session by calling the wizard:session_start MCP tool."` (via `hookSpecificOutput.additionalContext`). The actual memory brief loads only if the agent then calls `session_start`. So orientation depends on the agent obeying a nudge, and its payoff is invisible until it does.
2. **The `note` skill is a chore.** `src/wizard/skills/note/SKILL.md` gates every save behind four hard gates (session active, task identified, note-type decision tree, specificity), a mental-model step, and per-type templates — so saving gets avoided or half-done.

A third mechanism (a Stop-hook "you saved nothing" nudge) was considered and **deferred**: a soft nudge is the same failure mode we're fixing, a turn-count trigger causes alarm fatigue that *erodes* adoption, and it is not verifiable in the test suite. This spec leads with the two interventions that are automatic, quality-neutral, and verifiable.

---

## Design

### Section 1 — Proactive recall injection

Make orientation automatic and its payoff visible every session, without any ritual — a pure read, so it cannot regress Phase 2.

- **Testable brief-builder in wizard Python** (not a bash heredoc): `build_session_brief(db_path: str) -> str` — read-only, no LLM. Lives in a new module (e.g. `src/wizard/session_brief.py`) or alongside existing hook code. Exposed via a thin CLI subcommand `wizard hook session-brief` (mirroring how `stop.sh` calls `wizard hook stop`).
- **Content** — a compact, token-bounded snapshot (hard cap ≈ 25 lines / ~400 tokens; truncate deterministically if over):
  - open + blocked task counts (`LOWER(status) IN ('todo','in_progress','blocked')`);
  - the top 3–5 open tasks by the existing session-start ordering score (`repositories/task.py`: `stale_days==0` +40, in_progress +30, has-decision +15, ≥3 notes +15, tie-broken by last-worked), each with an `in_progress`/`stale_days` marker;
  - the most recent prior session's `summary` (one line, for continuity), if any.
- **Hook wiring** — `session-start.sh` Step 2 calls `wizard hook session-brief` and injects its output as `additionalContext`, **in addition to** the existing `session_start` instruction. Rationale: `session_start` (the MCP tool) still does the load-bearing lifecycle work — creating the `wizardsession` row and the `~/.wizard/sessions/<uuid>/wizard_id` file that capture (save_note anchoring, the Stop hook) depends on. The injected brief is additive orientation, not a replacement.
- Degrade gracefully: empty/missing DB → the hook still emits the existing instruction; the brief-builder returns "" and injection just omits the brief block.

### Section 2 — Fast-path note skill (docs-only)

Rewrite `src/wizard/skills/note/SKILL.md` so the **default is a single call**:

```
save_note(content=<specific finding>, note_type=<type>, task_id=<current task or omit>)
```

- Drop the four hard gates as *blockers*. Keep exactly one quality bar as guidance: **content must be specific** (a file path, function name, error, concrete finding, or explicit rationale).
- Keep `note_type` **explicit but trivial** — a one-line enum list (`investigation | decision | docs | learnings | failure | observation`), not the decision tree. **No silent default in the tool** — `note_type` stays a passed argument (silently defaulting to `INVESTIGATION` would re-introduce the mistyped-note pollution Phase 2 fought).
- `mental_model` mentioned once as optional; no mandatory template.
- Move the decision tree, per-type templates, and anti-patterns into a collapsed **"Thorough mode / reference"** section at the end, for when the agent chooses to be deliberate.

No code change to the `save_note` tool (`task_id` and the dedup/scrub path are already fine). This is a pure skill-content change; zero runtime risk.

### Section 3 — Measurement

- **Recall injection (unit-tested — the payoff of putting it in Python):** seed a temp migrated DB with tasks (varied status/scoring), notes, and sessions; assert `build_session_brief`:
  - returns the correct open/blocked counts,
  - lists the highest-scoring open tasks first (respecting the documented additive score),
  - includes the most recent session summary line,
  - stays within the length cap,
  - returns "" (or a minimal string) on an empty DB without raising.
  Plus a CLI smoke test: `wizard hook session-brief` prints the brief for a configured DB and exits 0.
- **Fast-path:** a test that `save_note(content=..., note_type=...)` succeeds in one call (no task/session prerequisite beyond what the tool already requires); a light assertion that the skill file's leading section is the one-call fast path.

---

## Success Criteria

- `build_session_brief` unit tests pass (counts, ordering, summary line, cap, empty-DB); `wizard hook session-brief` exits 0 and prints the brief.
- After deploy (reinstall + next session), the `SessionStart` context contains the actual task/summary brief, not just the "call session_start" instruction. (Manual confirmation — hook→Claude injection isn't unit-testable; the brief *content* is.)
- The rewritten note skill leads with the one-call fast path; `save_note` still works in a single call; `note_type` is never silently defaulted.
- No regression: `uv run pytest` green; ruff clean.

---

## Out of Scope (deferred)

- **Stop-hook capture nudge** — gated on (a) empirically verifying `Stop` `hookSpecificOutput.additionalContext` actually surfaces to the agent, and (b) a real "substantive work" trigger (not turn-count). Its own spec.
- **Ambient no-LLM capture** — heuristic higher-signal Stop-hook extraction.
- **Rebuilding LLM synthesis** (removed as "too slow and clunky") — not revisited here.
- Amplifier B (multi-entity embeddings) and the Phase 2 deferred amplifiers remain separate.

---

## Risks & Notes

- **Deploy:** hook + skill changes ship via the installed uv-tool copy — they take effect only after `uv tool install --force ~/repos/wizard` and (for the hook) the next session start / (for the skill) `wizard setup`/`refresh_skills`. No migration; the DB is untouched.
- **Token budget:** the brief is injected into every session's context — keep the cap tight and deterministic so it never balloons.
- **Brief staleness:** `stale_days`/scores are refreshed by `session_start` (the MCP tool) and at prior session ends; the hook reads whatever is current. The brief is a snapshot, not a live recompute — acceptable for orientation.
- **Fast-path vs quality:** cheaper capture leans on Phase 2's dedup + `mark_note` demotion + audit to stay clean. Keeping the specificity bar (and *not* auto-defaulting `note_type`) is what prevents a noise regression.
- The brief-builder must not open the DB read-write (use `?mode=ro` / a read-only connection) to avoid any lock contention with the running server.
