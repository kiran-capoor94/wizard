---
name: session-resume
description: Use when the engineer says 'continue', 'pick up where I left off', 'what was I working on', 'resume session', or opens a new thread mid-task
allowed-tools: mcp__wizard__resume_session mcp__wizard__task_start mcp__wizard__save_note mcp__wizard__what_am_i_missing mcp__wizard__update_task mcp__wizard__session_start ToolSearch Read
---

# Session Resume

## Role

You are **picking up a dropped thread**. Your job: restore prior session context faithfully, bring the engineer back up to speed, and set up continuity — without re-doing work that was already done.

---

## Hard Gates

Complete in order. Do not advance past a failed gate.

1. **`resume_session` called**
   - ✅ You received a `ResumeSessionResponse` with a new integer `session_id`
   - 🛑 If ToolError "No sessions with notes found": tell the engineer no prior session exists — call `session_start` instead.
   - 🛑 If ToolError "Session {id} not found": the requested session ID is invalid — ask for a different one.

---

## Steps

### Step 0 — Fetch Wizard Tool Schemas (if not already loaded)

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — Call `resume_session`

- If the engineer mentions a specific session (e.g. "resume session 42"): pass `session_id=42`
- Otherwise: call with no arguments. Wizard finds the most recent session with notes.

## Active Mode

If `active_mode` is set in the `resume_session` response, invoke the Skill tool with that skill name before doing anything else.
