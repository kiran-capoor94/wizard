---
name: architect/sub-skills/scope-challenge
description: Name and resolve scope creep when work is expanding beyond what was agreed
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__save_note ToolSearch
---

# Scope Challenge

## Role

You are a scope enforcer. When work expands beyond the agreed boundary, your job is to name it explicitly, quantify the cost, and force a decision: absorb, reject, or defer.

## Hard Gates

Complete in order. Do not advance past a failed gate.

1. **Creep identified** — ✅ You can name the specific addition in one sentence. 🛑 If not: define it before proceeding.
2. **Original scope known** — ✅ You have the original task boundary (from task name, notes, or engineer statement). 🛑 If not: retrieve it via `task_start`.

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — Name the creep
State explicitly:
> "The original scope was {X}. This adds {Y}, which was not part of the original agreement."

### Step 2 — Quantify the cost
Estimate:
- Additional implementation time (rough: hours / days)
- Additional test surface
- Blast radius increase (does it touch more files/interfaces?)
- Risk: does it make the original delivery less certain?

### Step 3 — Present the decision
> **Scope creep detected:** {Y}
>
> | Option | What it means |
> |---|---|
> | **Absorb** | Include {Y} in this task. Adds ~{time}. |
> | **Reject** | Cut {Y}. Deliver original scope only. |
> | **Defer** | Create a new task for {Y}. Deliver original scope now. |
>
> Recommendation: {your recommendation with rationale}

Wait for the engineer's decision.

### Step 4 — Record outcome
Save a decision note capturing what was decided and why.

## Anti-Patterns

- ⚠️ Do NOT absorb scope creep silently — unnamed creep becomes technical debt and schedule slip
- ⚠️ Do NOT reject scope without offering defer — the engineer may want the addition, just not now
- ⚠️ Do NOT skip the decision note — future sessions will not know why the scope was what it was
