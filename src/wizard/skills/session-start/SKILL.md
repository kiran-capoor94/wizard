---
description: Start a wizard session — syncs Jira and Notion, shows triage of open tasks, blocked tasks, and unsummarised meetings
---

# Session Start

Run at the beginning of every coding session.

## Steps

1. Call the `session_start` tool (no parameters needed)
2. Hold the returned `session_id` — you need it for `session_end`
3. Review the triage data:
   - **Blocked tasks** — address blockers first, they are costing time
   - **Unsummarised meetings** — summarise before context fades (use `wizard:meeting`)
   - **Open tasks** — sorted by priority then last-worked date
4. Review `sync_results` for any failed syncs — report failures to the engineer
5. Pick a task to work on and use `wizard:task-start`
