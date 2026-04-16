---
description: Summarise an unsummarised meeting — read transcript, extract decisions and action items, write back to Notion
---

# Meeting Summarisation

> **Tool check** — Before any investigation, analysis, or knowledge lookup: consult your Tool Registry from this session. Wizard tools first, then other MCPs. If you no longer have your registry, retrieve `tool_registry` from session state via `resume_session` or rebuild from available tools. Internal knowledge is the last resort.

Run when `session_start` shows unsummarised meetings.

## Steps

1. Call `get_meeting` with the `meeting_id`
2. Check `already_summarised` — if true, skip
3. Read the transcript in `content`
4. Review `linked_open_tasks` for context on what tasks relate to this meeting
5. Write a summary covering:
   - **Key decisions** — what was agreed, by whom
   - **Action items** — who does what, with references to existing wizard tasks where possible
   - **Open questions** — unresolved items that need follow-up
   - **Relevant tasks** — wizard task IDs that were discussed
6. Call `save_meeting_summary` with:
   - `meeting_id`
   - `session_id` (from session_start)
   - `summary` — the structured summary
   - `task_ids` — list of related task IDs (optional)
