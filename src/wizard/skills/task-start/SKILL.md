---
name: task-start
description: Use when the engineer selects a task to work on, says "let's work on task X", "start task X", or picks a task from the triage table
---

# Task Start

## Role

You are **resuming or beginning an investigation**. Your job: ground yourself in existing context, assess whether you're building on prior work or starting fresh, identify gaps, and brief the engineer before touching any code. You do not re-discover what was already found.

> **Tool check** — Before any investigation, analysis, or knowledge lookup: consult your Tool Registry. Wizard tools first, then other MCPs. If you no longer have your registry, retrieve `tool_registry` from session state via `resume_session` or rebuild from available tools. Internal knowledge is the last resort.

---

## Schema Reference

> **`TaskStartResponse`** — returned by `task_start`:
>
> - `task: TaskContext` — full task context (id, name, status, priority, category, due_date, stale_days, note_count, decision_count, source_url)
> - `compounding: bool` — `true` if prior notes exist, `false` if fresh start
> - `notes_by_type: dict[str, int]` — count per note type, e.g. `{"investigation": 3, "decision": 1}`
> - `rolling_summary: str | None` — synthesised digest of all prior notes built from mental_models, newest first. Present when ≥1 note has a mental_model recorded.
> - `prior_notes: list[NoteDetail]` — **3 most recent notes**, oldest first. For full history call `rewind_task`.
> - `total_notes: int` — total note count including notes not returned
> - `older_notes_available: bool` — `true` if total_notes > 3; use `rewind_task` to see older notes
> - `latest_mental_model: str | None` — most recent mental model snapshot, or null

> **`NoteDetail`** fields:
>
> - `id: int`, `note_type: str` (investigation | decision | docs | learnings)
> - `content: str` — full note text
> - `mental_model: str | None` — mental model captured with this note
> - `created_at: datetime`
> - `task_id: int | None`, `session_id: int | None`

---

## Hard Gates

1. **Session active**
   - ✅ You have a `session_id` from `session_start` or `resume_session`
   - 🛑 If not: you must call `session_start` first. `task_start` requires an active session.

2. **`task_start` called with valid `task_id`**
   - ✅ You received a `TaskStartResponse`
   - 🛑 If ToolError: surface the error. Common cause: invalid `task_id` — check the triage table from `session_start`.

3. **Prior notes read before any code action**
   - ✅ If `compounding == true`: you have read and summarised all `prior_notes` in your output
   - 🛑 If you are about to investigate code, run commands, or propose changes without reading prior notes: **STOP**. Read them first.

---

## Steps

### Step 1 — Call `task_start`

Call `task_start` with the `task_id` from the triage table.

### Step 2 — State Task Context

Render the task header:

> **Task {id} — {name}**
> Status: `{status}` | Priority: `{priority}` | Category: `{category}`
> Stale: {stale_days} days | Notes: {note_count} | Decisions: {decision_count}
> Source: [{source_url}]({source_url}) | Due: {due_date or "none"}

### Step 3 — Branch on `compounding`

```dot
digraph compounding {
    rankdir=TB;
    "compounding?" [shape=diamond];
    "Fresh start\n(Step 4A)" [shape=box, style=filled, fillcolor="#e8f5e9"];
    "Compounding session\n(Step 4B)" [shape=box, style=filled, fillcolor="#fff3e0"];

    "compounding?" -> "Fresh start\n(Step 4A)" [label="false"];
    "compounding?" -> "Compounding session\n(Step 4B)" [label="true"];
}
```

### Step 4A — Fresh Start (compounding == false)

No prior context exists. State:

> **Fresh start** — no prior notes for this task.

Then:
- If `source_url` exists: recommend reading the source (Jira ticket, Notion page) for context before investigating
- If no source: ask the engineer for context or begin investigation
- Proceed to Step 5.

### Step 4B — Compounding Session (compounding == true)

Prior work exists. Ground yourself in it before doing anything else.

**4B.1 — Show note shape:**

> **Prior work:** {total_notes} notes — {notes_by_type rendered as e.g. "3 investigations, 1 decision, 1 docs"}
> {if older_notes_available: "(showing 3 most recent — call rewind_task for full history)"}

**4B.2 — Restore mental model from rolling_summary:**

- If `rolling_summary` is not null:
  > **Rolling summary (built from mental models):**
  > {rolling_summary}
- Else if `latest_mental_model` is not null:
  > **Latest mental model:**
  > {latest_mental_model}
- If both null: flag this — "No mental models captured. The rolling summary will remain empty until mental_models are recorded on notes."

**4B.3 — Read the 3 most recent notes:**

Read `prior_notes` from **oldest to newest** (they arrive in this order). Extract:
- What was done most recently
- What was found or decided
- What open questions or next steps were noted

Render a **brief recap** — not a dump of raw content:

> **Recent activity** ({date range of prior_notes}):
> - {key finding or decision from most recent notes}
> - Open: {any unresolved questions from the notes}

**4B.4 — Identify what's already known vs. what's open:**

> **Established:** {from rolling_summary + recent notes — what is resolved}
> **Open:** {from rolling_summary + recent notes — what remains unresolved}

### Step 5 — Run Diagnostic

Call `what_am_i_missing` with the `task_id`. Surface any signals:

| Severity | Signal | Message |
|----------|--------|---------|
| `{severity}` | `{type}` | `{message}` |

If signals include `analysis_loop` or `no_decisions`: explicitly recommend making a decision before more investigation.

### Step 6 — Recommend Entry Point

Based on prior context (or lack thereof) and diagnostics, recommend how to begin:

- **Fresh + no source** → "Start by understanding the problem. What's the goal?"
- **Fresh + has source** → "Read the source ticket first: {source_url}"
- **Compounding + open questions** → "Pick up from: {first open question from Step 4B.4}"
- **Compounding + analysis loop signal** → "You have {n} investigations and no decisions. Recommend making a decision before investigating further."
- **Compounding + stale >= 5** → "Context is {stale_days} days old. Re-read the mental model and verify assumptions before continuing."

State the recommendation with the trigger:

> **Recommendation:** {action} — {reason grounded in fields}

The engineer always has final say.

---

## Reasoning Protocol

| Condition | Signal | Recommendation |
|-----------|--------|----------------|
| `compounding == true and rolling_summary == null and latest_mental_model == null` | No model captured | Recommend saving a mental model during this session to enable rolling_summary |
| `note_count > 3 and decision_count == 0` | Analysis loop | Decide before investigating further |
| `stale_days >= 5 and compounding == true` | Stale context | Re-validate assumptions, mental model may be outdated |
| `stale_days >= 7` | Severe context loss | Treat almost as fresh start — re-read everything, verify with code |
| `notes_by_type` has only `investigation` | No decisions, docs, or learnings | Flag: work is exploratory with no captured conclusions |
| `notes_by_type` has `decision` but no `investigation` | Decision without investigation | Flag: decision may lack grounding — verify rationale |

---

## Anti-Patterns

- ⚠️ Do NOT touch code before reading `rolling_summary` and recent notes when `compounding == true`. These ARE your starting point.
- ⚠️ Do NOT call `rewind_task` unless `older_notes_available == true` AND you believe the recent notes + rolling_summary are insufficient to proceed. Most sessions will not need it.
- ⚠️ Do NOT dump raw note content verbatim — synthesise into a brief recap.
- ⚠️ Do NOT re-investigate something already covered in the rolling_summary. If it says "ruled out approach X because Y", do not re-explore X.
- ⚠️ Do NOT ignore `rolling_summary` when it is present — it is the distilled understanding built from all prior mental models.
- ⚠️ Do NOT skip `what_am_i_missing` — it surfaces gaps you won't notice from notes alone.
- ⚠️ Do NOT begin work without stating the task context header — the engineer needs to confirm you're on the right task.
- ⚠️ Do NOT invent prior context. If `compounding == false`, say "fresh start" — do not speculate about what might have been done before.
- ⚠️ Do NOT neglect saving `mental_model` on notes — the rolling_summary is only as good as the mental models recorded. No mental_models = no rolling_summary.
