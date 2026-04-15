---
description: Start a wizard session — syncs Jira and Notion, shows triage of open tasks, blocked tasks, and unsummarised meetings
---

# Session Start

Run at the beginning of every coding session.

## Steps

### Step 0 — Build Tool Registry

Before calling any tool, enumerate every tool and MCP server available to you in this session. Do this now, before `session_start`.

- List **wizard tools first** (session lifecycle, tasks, notes, meetings, sync)
- Then list all other MCP servers grouped by provider, noting what each is for and when to prefer it over your internal knowledge
- Hold this as your **Tool Registry** for the session — you will reference it every time you would otherwise answer from memory
- You will save this registry when you call `session_end`

**Hard rule:** Before answering any question about how a library works, what an API supports, or what a codebase contains — stop and use a tool. Internal knowledge is the last resort, not the first.

### Step 1 — Call `session_start`

Call the `session_start` tool (no parameters needed).

### Step 2 — Hold `session_id`

Hold the returned `session_id` — you need it for `session_end`.

### Step 3 — Review triage data

- **Blocked tasks** — address blockers first, they are costing time
- **Unsummarised meetings** — summarise before context fades (use `wizard:meeting`)
- **Open tasks** — sorted by priority then last-worked date

### Step 4 — Check sync results

Review `sync_results` for any failed syncs — report failures to the engineer.

### Step 5 — Pick a task

Pick a task to work on and use `wizard:task-start`.
