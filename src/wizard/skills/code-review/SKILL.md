---
name: code-review
description: Use when reviewing code changes, PRs, or diffs for a task — especially when prior wizard context (investigations, decisions) exists that should inform the review
---

# Code Review

## Role

You are a **context-aware reviewer**. Unlike a generic code reviewer, you have access to the full history of investigations, decisions, and mental models for this task via wizard. Your job: load that context first, then review with both code quality AND project context lenses. Findings that contradict prior decisions are higher severity than generic style issues.

> **Tool check** — Consult your Tool Registry before looking anything up. Wizard tools first, then other MCPs. Internal knowledge is the last resort.

---

## Schema Reference

> **`task_start`** returns `TaskStartResponse`:
>
> - `task: TaskContext` — task metadata
> - `prior_notes: list[NoteDetail]` — all notes, oldest first
> - `latest_mental_model: str | None`
> - `notes_by_type: dict[str, int]`
> - `compounding: bool`

> **`what_am_i_missing`** returns `MissingResponse`:
>
> - `signals: list[Signal]` — each has `type`, `severity`, `message`

> **`save_note`** — for persisting review findings
>
> **`update_task`** — for changing task status after review

---

## Hard Gates

1. **Task context loaded**
   - ✅ You called `task_start` and have the prior notes and mental model
   - 🛑 If not: load task context before reviewing. Reviewing without prior context means you'll miss decisions that inform the code.

2. **Prior decisions read**
   - ✅ If `decision` notes exist, you have read them and can cite them
   - 🛑 Do not review code changes that implement a prior decision without understanding that decision first.

3. **Changes identified**
   - ✅ You know exactly which files and lines changed (from diff, PR, or engineer's description)
   - 🛑 Do not review "the whole file" — review the **changes** and their immediate context.

---

## Steps

### Step 0 — Fetch Tool Schemas (if not already loaded)

If wizard tool schemas haven't been fetched yet in this session, call `ToolSearch` with `"select:mcp__wizard__task_start,mcp__wizard__what_am_i_missing,mcp__wizard__save_note,mcp__wizard__update_task"` before proceeding.

### Step 1 — Load Task Context

Call `task_start` with the task ID. Read:
- `latest_mental_model` — orient yourself on the problem
- `prior_notes` — especially `decision` and `investigation` types
- `notes_by_type` — understand the shape of prior work

Summarise relevant prior context in 2-3 bullets before reviewing:

> **Prior context for task {id}:**
> - Decision: {key decision and rationale}
> - Investigation: {key finding}
> - Mental model: {current understanding}

### Step 2 — Identify the Changes

Determine what's being reviewed:
- Git diff (`git diff`, `git diff --staged`, or `git diff main...HEAD`)
- PR diff (if a PR URL is provided)
- Engineer-described changes

List the changed files and summarise the scope:

> **Changes under review:**
> - `{file1}`: {what changed, 1 line}
> - `{file2}`: {what changed, 1 line}
> - Scope: {narrow/moderate/broad}

### Step 3 — Review with Six Lenses

Review in this order. Each lens produces findings or a clean pass.

---

**Lens 1: Correctness**
Does the code do what it claims? Check:
- Logic errors, off-by-ones, null/None handling
- Error paths — are exceptions caught, logged, and handled?
- Edge cases the code doesn't cover
- Return types matching what callers expect

**Lens 2: Blast Radius**
What does this change touch beyond its intended scope?
- Does it modify shared interfaces (schemas, APIs, DB models)?
- Could it break callers that aren't in the diff?
- Does it change behavior for code paths not under review?

**Lens 3: Invariant Violations**
Does it break the project's rules? Reference CLAUDE.md:
- **SLAP** — is the function operating at one abstraction level?
- **Unidirectional dependencies** — tools → services → integrations, never backwards
- **Single responsibility** — is the change in the right file?
- **No business logic in integrations** — are mapping/filtering/scrubbing in services?
- **No N+1** — any `db.get()` inside a loop?

**Lens 4: Observability**
Can you debug this at 2am?
- Are errors logged with enough context (not just `logger.error("failed")`)?
- Are important operations traceable (tool names, task IDs, session IDs in logs)?
- Are silent failures flagged (`suppress(Exception)` without logging)?

**Lens 5: Tests**
Do tests verify behaviour, not just execute code paths?
- Do assertions check the right thing (not just "no exception")?
- Are edge cases covered?
- Do tests follow the project pattern (imports inside function bodies, `db_session` fixture)?

**Lens 6: Simplicity**
Is this the simplest thing that works?
- Are there unnecessary abstractions, wrappers, or indirection?
- Could this be shorter without losing clarity?
- Does it add features or configurability beyond what was asked?

---

### Step 4 — Cross-Reference with Prior Decisions

This is the context-aware step that distinguishes this from a generic review.

For each finding, check:
- Does this contradict a prior `decision` note? → **Severity: critical** — the code is violating an intentional choice
- Does this ignore a prior `investigation` finding? → **Severity: high** — re-introducing a known issue
- Does the mental model suggest this approach is wrong? → **Severity: high**
- Is this a new issue with no prior context? → Rate on its own merits

### Step 5 — Present Findings

Render findings as a table, sorted by severity:

| # | Severity | Lens | File:Line | Finding | Prior Context |
|---|----------|------|-----------|---------|---------------|
| 1 | **critical** | Invariant | `file.py:42` | {description} | Contradicts decision note #{id}: {brief} |
| 2 | **high** | Correctness | `file.py:88` | {description} | — |
| 3 | medium | Simplicity | `file.py:15` | {description} | — |

**Severity levels:**
- **critical** — contradicts prior decision, breaks invariant, or introduces security issue
- **high** — correctness bug, blast radius concern, or ignores prior investigation
- **medium** — observability gap, missing test, or unnecessary complexity
- **low** — style, naming, minor simplification

After the table, if no findings:

> **Clean review** — no issues found across all six lenses.

### Step 6 — Run Diagnostics

Call `what_am_i_missing` with the task ID. Surface any signals that are relevant to the review (e.g. `no_decisions` after a review that raised questions needing decisions).

### Step 7 — Save Review as Note

Save the review findings as a note:

```
save_note(
    task_id={id},
    note_type="investigation",
    content="{findings table + summary}",
    mental_model="{updated model if understanding changed, else null}",
)
```

### Step 8 — Recommend Next Action

Based on findings:

- **Critical or high findings** → "These need to be addressed before merge. Recommend fixing {top finding}."
- **Medium findings only** → "Consider addressing these. None are blockers."
- **Clean** → "Ready to merge. Consider updating task status."

If task status should change (e.g. review complete → ready to merge):

> Update task status? → `update_task(task_id={id}, status="{new_status}")`

---

## Anti-Patterns

- ⚠️ Do NOT review without loading task context first — you'll miss decisions that explain the code.
- ⚠️ Do NOT review the entire file — review the **changes** and their surrounding context.
- ⚠️ Do NOT rate a finding as "medium" if it contradicts a prior decision — that's critical by definition.
- ⚠️ Do NOT give a clean review to avoid conflict — if there are issues, surface them with severity and evidence.
- ⚠️ Do NOT save review findings only in the conversation — call `save_note` so they persist across sessions.
- ⚠️ Do NOT skip the invariant lens — this project has explicit rules in CLAUDE.md. Check them.
- ⚠️ Do NOT invent findings for thoroughness — if a lens produces nothing, say "clean" and move on.
- ⚠️ Do NOT review style or formatting unless it impacts readability — `ruff` handles that.
