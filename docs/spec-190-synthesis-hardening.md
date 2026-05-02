# Spec §190 — Synthesis Note Parsing Hardening

**Task:** #190 — Harden synthesis note parsing — decouple task matching from LLM, defensive schema coercion
**Status:** Track A ready to implement. Track B blocked on offline experiment.
**Last updated:** 2026-04-24

---

## Problem Statement

The synthesis pipeline conflates two concerns:

1. **Note generation** — what happened in the session? (`note_type`, `content`, `mental_model`)
2. **Task association** — which task does each note belong to? (`task_id`)

The LLM is asked to produce both in a single response. This causes:

- **Silent wrong associations** — LLM returns a valid `task_id` that is contextually wrong (session about task 42, model returns task 37 because names are similar). No runtime detection. Task state signals degrade quietly.
- **Schema violations** — `task_id` returned as a list, string, or float fails or corrupts Pydantic validation, silently discarding notes.
- **Hallucinated IDs** — task IDs not in `valid_task_ids` are silently dropped to session anchor.
- **Invalid `note_type`** — unrecognised strings are silently coerced to `INVESTIGATION` downstream rather than at the parse boundary.

The most dangerous failure is wrong-but-valid task association: it corrupts `task_state` signals, `what_should_i_work_on` scoring, and rolling summaries with no visible error.

---

## Scope

### In scope

- **Track A:** Harden `_coerce_note` in `llm_adapters.py` with defensive coercions for all schema fields
- **Track A:** Consolidate `note_type` normalisation into the parse boundary (currently handled loosely downstream)

### Out of scope

- **Track B** (decoupled task matching): blocked on offline experiment — see below
- **Retroactive re-matching** of historical notes: deferred indefinitely (users don't feel this pain)
- **Many-to-many note anchoring**: deferred until Track B proves out

---

## Track A — Defensive `_coerce_note` Hardening

### Target file

`src/wizard/llm_adapters.py` — `_coerce_note(n: dict) -> dict`

### Coercions to add

| Field          | LLM quirk                     | Current behaviour                                     | Required behaviour                                                                                                                                                                    |
| -------------- | ----------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task_id`      | List (e.g. `[177, 178, 131]`) | Coerced to `None` ✓                                   | Already handled                                                                                                                                                                       |
| `task_id`      | String integer (`"177"`)      | Pydantic `ValidationError` → note discarded           | Coerce `int("177")` → `177`; `ValueError` → `None`                                                                                                                                    |
| `task_id`      | Float (`177.0`)               | Pydantic `ValidationError` → note discarded           | Coerce `int(177.0)` → `177`                                                                                                                                                           |
| `note_type`    | Any string value              | Silent mis-classification in `_save_notes` downstream | Lowercase + strip at parse boundary; map synonyms                                                                                                                                     |
| `note_type`    | Synonym values                | Silent mis-classification                             | Map: `"finding"` → `"investigation"`, `"choice"` / `"option"` → `"decision"`, `"summary"` → `"session_summary"`, `"doc"` / `"documentation"` → `"docs"`, `"learning"` → `"learnings"` |
| `content`      | `None` or non-string          | Pydantic `ValidationError` → note discarded           | `str(n.get("content") or "")`                                                                                                                                                         |
| `content`      | Empty string                  | Blank note written to SQLite                          | Skip note (return sentinel or filter in caller)                                                                                                                                       |
| `mental_model` | List of strings               | Pydantic `ValidationError` → note discarded           | Join with `"\n"`                                                                                                                                                                      |

### Constraints

- `_coerce_note` must remain under C901 complexity limit (10)
- If the coercions push complexity over 10, extract a helper per field group
- All coercions are pure dict mutations — no DB access, no I/O
- Do not raise from `_coerce_note` — return the best-effort coerced dict and let validation surface irrecoverable failures

### Tests to add (in `tests/scenarios/test_synthesis_failure.py`)

Extend the existing scenario class or add new module-level functions:

- `test_parse_notes_coerces_task_id_string_to_int` — `"task_id": "177"` → `task_id == 177`
- `test_parse_notes_coerces_task_id_float_to_int` — `"task_id": 177.0` → `task_id == 177`
- `test_parse_notes_normalises_note_type_case` — `"note_type": "Investigation"` → `note_type == "investigation"`
- `test_parse_notes_maps_note_type_synonym` — `"note_type": "finding"` → `note_type == "investigation"`
- `test_parse_notes_coerces_null_content` — `"content": null` → either skipped or empty string (decide at implementation time)
- `test_parse_notes_coerces_mental_model_list` — `"mental_model": ["point 1", "point 2"]` → single string

All tests follow the existing pattern in `test_synthesis_failure.py`:

```python
def test_parse_notes_coerces_X():
    raw = json.dumps([{...}])
    notes = _parse_notes(raw)
    assert ...
```

### File size check

`llm_adapters.py` is currently 217 lines. Track A additions are small (≤30 lines). No cap risk.
`test_synthesis_failure.py` is currently 180 lines. Adding 6 tests (~60 lines) → ~240 lines. No cap risk.

---

## Track B — Decoupled Task Matching (BLOCKED)

### What it is

Remove `task_id` from the LLM-facing prompt entirely. After `generate_notes()` returns, a deterministic pass assigns `task_id` values based on word-overlap between note content and open task names.

### Why it's blocked

The hypothesis — deterministic matching produces a net improvement over LLM matching — is **unvalidated**. A word-overlap matcher that performs worse than the LLM on generic task names would be a regression.

### Unblocking condition

Run an offline experiment:

1. Take 15–20 recent synthesised sessions from `~/.wizard/wizard.db` (query `wizardsession` where `is_synthesised = true` and `transcript_raw IS NOT NULL`)
2. For each session, strip existing `task_id` associations from notes
3. Run the proposed word-overlap matcher against the note content + open task list
4. Compare matcher output to original LLM output (discounting known hallucinations)
5. **Pass threshold:** matcher correctly assigns ≥80% of notes the LLM associated correctly

Only start Track B implementation after the experiment passes.

### Proposed architecture (for reference, not approved for implementation)

```
synthesise_path()
  ├── prepare_task_table()     → task_ids: set[int], task_name_map: dict[int, str]
  ├── generate_notes()         → list[SynthesisNote]  (no task_id in LLM output)
  ├── match_tasks()            → list[SynthesisNote]  (task_id assigned by matcher)
  └── persist()                → writes Note rows
```

`match_tasks(notes, task_name_map, threshold=0.3)` — pure function, no DB access.
Matching: lowercased token intersection score = `|note_tokens ∩ task_tokens| / |task_tokens|`.
Notes below threshold get `task_id = None`.

### Open questions (must resolve before Track B)

1. **Task name quality** — are most open tasks Jira-keyed (`ENG-421: Fix redirect`) or generic (`investigation`, `spike`)? Determines matcher viability.
2. **Multi-task anchoring** — can a note match more than one task? If yes → schema migration (many-to-many). Decision: keep one-to-one for now (highest-score match wins), revisit if data shows multi-task is common.
3. **Confidence threshold** — what miss rate is acceptable? Start at 0.3, tune from experiment data.
4. **`SynthesisNote` schema change** — `task_id` becomes an output-only field populated by the matcher, not the LLM. Prompt changes required in `synthesis_prompt.py`.
5. **Context window impact** — removing the task table from the prompt frees budget for more transcript content. Quantify improvement in experiment.

---

## Acceptance Criteria

### Track A

- [ ] `_coerce_note` handles all field quirks in the table above
- [ ] All new scenario tests pass: `uv run pytest tests/scenarios/test_synthesis_failure.py`
- [ ] Full test suite passes: `uv run pytest`
- [ ] No file exceeds 500 lines
- [ ] No function exceeds C901 complexity 10
- [ ] `wizard capture` successfully synthesises a session with a transcript that previously failed due to `task_id` list/string violations

### Track B (future gate)

- [ ] Offline experiment passes (≥80% match rate)
- [ ] Open questions resolved
- [ ] Implementation plan reviewed before starting

---

## Key Files

| File                                        | Role                                                                  |
| ------------------------------------------- | --------------------------------------------------------------------- |
| `src/wizard/llm_adapters.py`                | `_coerce_note`, `_parse_notes` — parse boundary                       |
| `src/wizard/synthesis.py`                   | `Synthesiser` — orchestration, `_save_notes`, `valid_task_ids` filter |
| `src/wizard/schemas.py`                     | `SynthesisNote` — Pydantic model                                      |
| `src/wizard/models.py`                      | `Note`, `WizardSession` — ORM                                         |
| `tests/scenarios/test_synthesis_failure.py` | All synthesis scenario tests                                          |
