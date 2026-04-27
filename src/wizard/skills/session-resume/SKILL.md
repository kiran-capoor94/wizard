---
name: session-resume
description: Use when the engineer says "continue where I left off", "pick up from yesterday", "what was I working on", or opens a new thread mid-task
---

# Session Resume

## Role

You are **picking up a dropped thread**. A prior session exists with state, notes, and context. Your job: restore that context faithfully, bring the engineer back up to speed, and set up continuity — without re-doing work that was already done.

> **Tool check** — Consult your Tool Registry after restoration. Internal knowledge is the last resort.

---

## Hard Gates

1. **`resume_session` called**
   - ✅ You received a `ResumeSessionResponse` with a new integer `session_id`
   - 🛑 If ToolError "No sessions with notes found": tell the engineer no prior session exists — call `session_start` instead.
   - 🛑 If ToolError "Session {id} not found": the requested session ID is invalid — ask for a different one.

---

## Steps

### Step 0 — Fetch Wizard Tool Schemas (if not already loaded)

If wizard tool schemas haven't been fetched yet in this session, call `ToolSearch` with `"select:mcp__wizard__resume_session,mcp__wizard__task_start,mcp__wizard__save_note,mcp__wizard__what_am_i_missing,mcp__wizard__rewind_task,mcp__wizard__update_task,mcp__wizard__session_end"` before proceeding.

### Step 1 — Call `resume_session`

- If the engineer mentions a specific session (e.g. "resume session 42"): pass `session_id=42`
- Otherwise: call with no arguments. Wizard finds the most recent session with notes.

## Active Mode

If `active_mode` is set in the `resume_session` response, invoke the Skill tool with that skill name before doing anything else.
