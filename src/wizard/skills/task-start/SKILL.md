---
name: task-start
description: Use when the engineer selects a task to work on, says "let's work on task X", "start task X", or picks a task from the triage table
---

# Task Start

## Role

You are **resuming or beginning an investigation**. Your job: ground yourself in existing context, assess whether you're building on prior work or starting fresh, identify gaps, and brief the engineer before touching any code. You do not re-discover what was already found.

> **Tool check** — Before any investigation, analysis, or knowledge lookup: consult your Tool Registry. Wizard tools first, then other MCPs. If you no longer have your registry, retrieve `tool_registry` from session state via `resume_session` or rebuild from available tools. Internal knowledge is the last resort.

---

## Hard Gates

1. **Session active**
   - ✅ You have a `session_id` from `session_start` or `resume_session`
   - 🛑 If not: you must call `session_start` first. `task_start` requires an active session.

---

## Steps

### Step 1 — Call `task_start`

Call `task_start` with the `task_id` from the triage table.
