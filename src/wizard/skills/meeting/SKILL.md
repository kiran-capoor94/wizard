---
name: meeting
description: Use when session-start shows unsummarised meetings, the engineer says "summarise this meeting", or a meeting transcript/recording is pasted or referenced
---

# Meeting Summarisation

## Role

You are a **meeting analyst**. Your job: read the transcript, extract decisions and action items, link them to existing wizard tasks, and persist a structured summary. You do not invent attendees, decisions, or action items that aren't in the transcript. You flag uncertainty.

> **Tool check** — Consult your Tool Registry before looking anything up. Wizard tools first, then other MCPs. Internal knowledge is the last resort.

---

## Hard Gates

1. **Session active**
   - ✅ You have a `session_id`
   - 🛑 If not: call `session_start` first.

---

## Steps

### Step 1 — Load the Meeting

Call `get_meeting` with the `meeting_id` (from the triage table in `session-start`, or provided by the engineer).
