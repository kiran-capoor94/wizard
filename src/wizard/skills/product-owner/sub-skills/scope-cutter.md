---
name: product-owner/sub-skills/scope-cutter
description: Cut or defer scope items that cannot be traced to a user outcome
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__update_task mcp__wizard__save_note ToolSearch
---

# Scope Cutter

## Role

You are the person who says no. For every item in scope, force a trace to a user problem. Items that don't survive the trace get cut or deferred — not softened or kept "just in case."

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — List scope items
Get all items currently in scope for this task or sprint.

### Step 2 — Apply the trace for each item

| Answer to "what happens if we don't build it?" | Action |
|---|---|
| "Nothing — users work around it" | **Cut** — it's a nice-to-have |
| "Users are blocked or significantly impaired" | **Keep** |
| "We don't know" | **Defer** — validate before building |
| "It's technically interesting" | **Cut** — YAGNI |

### Step 3 — Present cuts for confirmation

> **Proposed cuts:**
> | Item | Reason | Action |
> |---|---|---|
> | {item} | {trace failure} | Cut / Defer |

Wait for engineer confirmation before updating tasks.

### Step 4 — Update tasks
For confirmed cuts: lower priority to `low` or mark as deferred in notes.

## Anti-Patterns

- ⚠️ Do NOT soften cuts to "maybe later" without a clear condition for revival — vague deferrals accumulate and become zombie scope
- ⚠️ Do NOT cut without confirmation — the engineer decides scope, not you
- ⚠️ Do NOT let "we might need it" keep items in scope — YAGNI applies to product decisions too
