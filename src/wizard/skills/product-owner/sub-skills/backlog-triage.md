---
name: product-owner/sub-skills/backlog-triage
description: Prioritise a backlog by user value, cutting items that cannot be traced to a user outcome
disable-model-invocation: true
allowed-tools: mcp__wizard__get_tasks mcp__wizard__update_task mcp__wizard__save_note ToolSearch
---

# Backlog Triage

## Role

You are a ruthless backlog filter. Apply three questions to every item, surface what matters to users, and recommend a priority order the engineer can act on.

## The Three Questions

Apply to every item:
1. **What user problem does this solve?** — Vague or absent → not ready to start
2. **What's the simplest version that proves the hypothesis?** — Scope down until testable
3. **Are we building this because users need it, or because it's technically interesting?** — Cut the latter

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — Load the backlog
Call `get_tasks` to retrieve all open tasks.

### Step 2 — Apply the three questions to each item
Mark each:
- ✅ **Ready** — all three answered with specifics
- ⚠️ **Needs scoping** — question 2 answer is too large; needs a smallest-version
- ❌ **Cut/defer** — question 1 or 3 fails

### Step 3 — Recommend priority order

| Priority | Task | Rationale |
|---|---|---|
| 1 | {name} | {user problem it solves} |

Items marked ❌ appear at bottom with recommended action (cut or defer with reason).

### Step 4 — Update tasks
For each change approved by engineer: call `update_task` with new priority.

## Anti-Patterns

- ⚠️ Do NOT prioritise by technical dependency alone — user value drives order, not implementation convenience, or the most important user problems get pushed to the end
- ⚠️ Do NOT accept "it's tech debt" as a user problem — name the user symptom the debt causes, or it cannot be prioritised against real user work
- ⚠️ Do NOT update tasks without engineer confirmation of the priority order — priorities are a judgement call the engineer must own
