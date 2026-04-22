---
name: session-end
description: Use when the engineer says "let's wrap up", "end session", "I'm done for today", "closing time", or conversation is ending
---

# Session End

## Role

You are **closing a shift**. Your job: collect a structured summary of what happened, persist it so the next session can resume seamlessly, and write back to Notion. You do not invent fields the engineer didn't provide. You do not skip fields. You verify before calling the tool.

> **Tool check** — Consult your Tool Registry if you need to look anything up. Internal knowledge is the last resort.

---

## Hard Gates

1. **`session_id` available**
   - ✅ You have an integer `session_id` from this session
   - 🛑 If lost: check conversation history. If truly lost, tell the engineer — you cannot call `session_end` without it.

2. **All 8 parameters collected**
   - ✅ You have values for `summary`, `intent`, `working_set`, `state_delta`, `open_loops`, `next_actions`, `closure_status`, and `tool_registry`
   - 🛑 If any parameter is missing: ask the engineer for it. Do not call with placeholders or invented values.

3. **PII check passed**
   - ✅ You have reminded the engineer that `open_loops` and `next_actions` are stored unscrubbed
   - 🛑 If the engineer's input contains obvious PII (names, emails, patient data): flag it and ask them to rephrase before calling.

---

## Steps

### Step 1 — Draft from Context

Before asking the engineer, **draft as many fields as you can** from what happened in this session. You were present — use that context.

Review:
- Which tasks were worked on → `working_set`
- What was the goal when the session started → `intent`
- What changed (tasks completed, blockers resolved, new findings) → `state_delta`
- What's still unresolved → `open_loops`
- What should happen next → `next_actions`
- How did the session end → `closure_status`

### Step 2 — Present Draft for Confirmation

Present your draft to the engineer in a structured format:

> **Session {session_id} — closing summary:**
>
> | Field | Draft |
> |-------|-------|
> | **Summary** | {your draft} |
> | **Intent** | {your draft} |
> | **Working set** | {task IDs as list} |
> | **State delta** | {your draft} |
> | **Open loops** | {list, or "none"} |
> | **Next actions** | {list, or "none"} |
> | **Closure status** | `{clean/interrupted/blocked}` |
>
> Does this look right? Edit anything that's off.

**Do not ask each field one at a time** unless the engineer prefers it. Present the full draft and let them correct.
