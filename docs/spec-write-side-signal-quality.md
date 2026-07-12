# Spec — Write-Side Signal Quality (the note "immune system")

**Task:** unassigned (track in wizard once implementation starts)
**Status:** Approved design, ready to implement.
**Last updated:** 2026-07-13
**Scope:** Thread E, Phase 2 of 3. Phase 1 (retrieval engine) is merged. Phase 3 (adoption ergonomics) is deferred to its own spec.

---

## Problem Statement

Phase 1 fixed recall. That makes the write side the binding constraint — and because recall now surfaces everything well, existing noise is *more* visible, not less. The write side has no immune system: nothing filters low-signal notes at intake, and the designed-but-never-wired demotion lifecycle means no note is ever marked wrong or outdated. Three code-level roots, each confirmed against the live DB (17 notes at time of writing):

1. **The demotion machinery is 100% dormant — and recall wouldn't honour it.** `note.status` (active/superseded/contradicted/archived/invalid/unclassified), `supersedes_note_id`, and `reference_count` are columns added in the v3 "artifact identity" migration (`alembic/versions/f0fb7ac74c46_artifact_identity.py:36-38`) that **no application code ever writes** to a non-default value. Live DB: 17/17 `active`, 0 supersedes, all `reference_count=0`. Worse, the recall read paths ignore status entirely — `NoteRepository.get_for_task` (`repositories/note.py:33-46`), `get_notes_grouped_by_task` (`note.py:48-62`), and the search note metadata fetch (`repositories/search.py:136`) have no status filter. So activating demotion is a **two-sided** job: something must set status, *and* recall must exclude demoted notes.

2. **Live noise is machine boilerplate.** The abandoned-session auto-closer (`services.py:303-310`) writes a `SESSION_SUMMARY` **note** whose content is the synthetic string `"Auto-closed: N note(s) across M task(s)…"` (`_synthetic_summary`, `services.py:329-338`) — 4 of the 17 live notes are exactly this zero-signal boilerplate. The Stop-hook `OBSERVATION` firehose (`cli/hooks.py:70-94`) is a latent landmine: a raw `INSERT` with **no PII scrub**, no `content_hash`, no dedup, no quality gate beyond a 50-char length check. (The session-end transcript-synthesis firehose is **dead code** — removed in commit `4aafb76`; it produces zero notes and is not part of this spec.)

3. **Dedup is exact-hash, per-task, un-normalized.** `_prepare_note_fields` (`tools/task_tools.py:193-202`) hashes raw scrubbed content with no whitespace/trim normalization, scoped to one `task_id`. Trivial variants (trailing space, case) defeat it; the OBSERVATION path skips dedup entirely.

---

## Design

Two stages, sequenced and independently shippable, plus measurement. Stage 2a is a pure write-side quality gate (no schema change). Stage 2b activates the existing status columns end-to-end.

### Stage 2a — Intake gate (no schema change)

**2a-1. Stop writing the "Auto-closed" boilerplate note.** In `SessionCloser` (`services.py:288-317`), when the summary is synthetic (`closed_via == "synthetic"` from `_synthetic_summary`), set `session.summary` and `closed_by` as today but **skip the `Note(...)` creation + `self._note_repo.save(...)`** (`services.py:303-310`). The session row already records closure; no memory-worthy note exists for an interrupted session. Real user-authored session summaries (non-synthetic path) still become notes.

**2a-2. Harden the OBSERVATION firehose** (`cli/hooks.py:70-94`). Route the observation write through the same intake path `save_note` uses instead of a bare `INSERT`: PII-scrub the content, compute `content_hash` over the normalized content (2a-3), and dedup — skip the write if it duplicates the most recent active note for the resolved task. Preserve the existing gates (≥50 chars, safe session id, resolved task id) and the <150ms budget. Closes a real privacy gap (observations are currently unscrubbed) and caps the firehose before it can fire.

**2a-3. Normalize before hashing** in `_prepare_note_fields` (`task_tools.py:193-202`). Hash a normalized form of the scrubbed content — `strip()` + collapse runs of internal whitespace to a single space — instead of the raw bytes. Keep case (avoid over-merging genuinely distinct content). Store the original content; only the *hash input* is normalized. Catches trailing-space/reflow near-duplicates. Cross-task and semantic dedup remain out of scope.

### Stage 2b — Demotion machinery (activates existing columns)

**2b-1. Read-side active-only filters (the enabler).** `active` is the **sole recall-eligible status** — recall excludes every other status (superseded, contradicted, invalid, **archived**, **unclassified**). The filter is literally `status == 'active'`. Add it as opt-in so recall excludes non-active notes while history views keep them:
- `NoteRepository.get_for_task` (`note.py:33-46`) — add `active_only: bool = False` param; when true, `WHERE status == 'active'`. Recall callers pass `active_only=True`: `task_start` `_select_key_notes` (`tools/task_tools.py:147,153`) and `get_task` (`tools/query_tools.py:132`). `rewind_task` (`tools/note_tools.py:41`) passes `active_only=False` (full history, with status shown).
- `get_notes_grouped_by_task` (`note.py:48-62`) — same `active_only` param; resume (`session_tools.py` `_group_prior_notes`) passes `True`.
- Search note fetch (`search.py:136-140`) — add `AND status = 'active'` to the `WHERE id IN :ids` metadata query, so demoted notes never appear in search results even if their FTS/vec rows still match. (The FTS/vec index tables have no status column; filtering at the metadata join is correct and sufficient.)

**2b-2. A `mark_note` MCP tool** (new, in `tools/note_tools.py`; register in `tools/__init__.py`). Signature: `mark_note(note_id: int, status: str, superseded_by_note_id: int | None = None) -> MarkNoteResponse`. Sets `note[note_id].status` to one of superseded/contradicted/invalid/archived/active (validated against `NoteStatus`).

Column-semantics convention (`supersedes_note_id` lives on the *winning* note and means "this note supersedes note X"): when `superseded_by_note_id` is supplied, the tool performs the two-sided link in one call — it sets `note[note_id].status = 'superseded'` **and** sets `note[superseded_by_note_id].supersedes_note_id = note_id` (the newer note records that it replaced the older). `superseded_by_note_id` is only meaningful with `status='superseded'`; reject the combination otherwise. Fully reversible: `mark_note(note_id, 'active')` clears the demotion (and, if it was a superseded target, the tool clears the corresponding `supersedes_note_id` back-link). No LLM. Returns the updated note's id + new status.

**2b-3. Teach the `note` skill** (the agent-facing skill that drives `save_note`) when to call `mark_note`: when a new finding contradicts or supersedes a recorded one, demote the old note rather than leaving both to compete in recall. (Skill lives in the agent skills dir, mirrored from `src/wizard/skills/` — update the source.)

Deferred amplifiers: LLM auto-supersession at save-time (gated on the measurement below), cross-task/semantic dedup, and `reference_count`-based decay of never-surfaced notes.

### Stage 3 — Measurement

**Committed behaviour tests** (`tests/scenarios/`):
- Auto-closed abandoned session sets `session.summary` but creates **no** note.
- OBSERVATION write scrubs PII, computes `content_hash`, and skips a verbatim duplicate.
- Normalized dedup: content differing only by trailing/collapsed whitespace dedups to one note.
- A demoted (`status != 'active'`) note is **excluded** from `get_for_task(active_only=True)`, `get_notes_grouped_by_task(active_only=True)`, and `hybrid_search`, but **still returned** by `rewind_task`.
- `mark_note` sets status + `supersedes_note_id`, and reverting to `active` restores visibility.
- End-to-end: a search returns note N; after `mark_note(N, 'superseded')`, the same search no longer returns N.

**Local noise-audit script** (`scripts/audit_note_quality.py`, read-only, not CI). Opens the real DB read-only and reports corpus health: note_type distribution, % synthetic/boilerplate, % demoted by status, task-anchored ratio, exact/normalized duplicate counts. Run before/after to see the noise drop and track demotion uptake.

---

## Success Criteria

- After 2a: no new `"Auto-closed…"` notes are created (verified by test + the audit script showing the boilerplate count stop growing); OBSERVATION writes are PII-scrubbed and de-duplicated; whitespace-variant content dedups.
- After 2b: demoting a note removes it from all recall paths (task_start, get_task, resume, search) while `rewind_task` still shows it; `mark_note` is reversible; all existing tests still pass.
- The noise-audit script runs against the live DB and prints the corpus-health report.
- No regression: `uv run pytest` green.

---

## Out of Scope (deferred)

- **LLM auto-supersession** at save-time (embedding-similarity + judge). Higher-value self-cleaning, but adds save latency and risks *false demotion = silent memory loss*. Gated on the audit showing manual `mark_note` uptake is insufficient. Its own spec.
- **Cross-task and semantic (paraphrase) dedup.**
- **`reference_count`-based decay** — incrementing on recall surface, decaying never-referenced notes.
- **Rebuilding session-end synthesis** (currently dead code) — separate effort if desired.
- Phase 3 (adoption ergonomics).

---

## Risks & Notes

- **Skipping the auto-close note** must not break anything reading `SessionCloser`'s return (`ClosedSessionSummary` still returns the summary text; only the persisted Note is skipped). Verify no caller depends on the note existing.
- **Opt-in read filter default is `False`** so no existing caller silently changes behaviour; only the named recall callers pass `True`. This keeps the change surgical and auditable.
- **`mark_note` convention** (winning note's `supersedes_note_id` → the note it replaced; replaced note's `status` → superseded, set together via the tool's `superseded_by_note_id` arg) must be documented on the tool and in the note skill to avoid ambiguity.
- **Observation dedup** compares against the most recent active note for the resolved task; it must not accidentally suppress legitimately distinct consecutive observations — scope the dedup to exact normalized-hash match, not similarity.
