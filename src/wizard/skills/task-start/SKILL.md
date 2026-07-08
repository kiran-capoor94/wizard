---
name: task-start
description: Use when the engineer picks a task, says 'start task X', 'let's work on X', 'begin task', or selects from the triage table
allowed-tools: mcp__wizard__task_start mcp__wizard__what_am_i_missing mcp__wizard__save_note mcp__wizard__rewind_task mcp__wizard__update_task ToolSearch Bash Read Grep Glob
---

# Task Start

## Role

You are **resuming or beginning an investigation**. Your job: ground yourself in existing context, assess whether you're building on prior work or starting fresh, identify gaps, and brief the engineer before touching any code. You do not re-discover what was already found.

---

## Hard Gates

Complete in order. Do not advance past a failed gate.

1. **Session active**
   - ✅ You have a `session_id` from `session_start` or `resume_session`
   - 🛑 If not: you must call `session_start` first. `task_start` requires an active session.

---

## Requirement Discovery (Grill Phase)

Before stating the success criterion:
1. Identify the 2–3 biggest assumptions baked into the task name or most recent note
2. For each assumption, ask the user one question to confirm or refute it
3. Ask questions one at a time — wait for answer before next question
4. Stop when: all major branches resolved, OR user says "enough" / "proceed"
5. State the success criterion incorporating what you learned

Skip if:
- Task has 3+ decisions already recorded
- Task name + notes fully specify the work with no ambiguous branches
- User opens with "just do it" or equivalent

---

## Success Criterion

Before writing any code, state the verifiable success criterion for this task:
what specific, observable outcome confirms it is done?

- If you can state it: proceed.
- If you cannot state it: ask the user before proceeding.

Examples of good success criteria:
- "The test `test_save_note.py` passes and note content in the DB matches the scrubbed input verbatim"
- "Running `wizard search 'JWT failure'` returns the note written in this session"
- "The dashboard loads at localhost:8501 showing synthesis health for last 10 sessions"

---

## Steps

### Step 1 — Fetch Wizard Tool Schemas (if not already loaded)

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 2 — Call `task_start`

Call `task_start` with the `task_id` from the triage table.
