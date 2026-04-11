---
description: End a wizard session — summarise what changed, what is still open, and what matters next session
---

# Session End

Run at the end of every coding session.

## Steps

1. Review what was accomplished this session
2. Write a summary covering:
   - **What changed** — files modified, features added, bugs fixed
   - **What is still open** — tasks in progress, blockers, unfinished items
   - **What matters next session** — where to pick up, what to investigate, what is time-sensitive
3. Call `session_end` with:
   - `session_id` (from session_start)
   - `summary` — the structured summary
4. The summary is persisted as a SESSION_SUMMARY note and written to the Notion daily page
