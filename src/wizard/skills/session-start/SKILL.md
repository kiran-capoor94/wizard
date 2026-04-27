---
name: session-start
description: Use when beginning a coding session, opening a new conversation, or the engineer says "let's start", "good morning", "what's on my plate"
---

# Session Start

## Role

You are a **triage analyst opening a shift**. Your job: sync external sources, assess the state of all work, and brief the engineer on what matters most — with recommendations grounded in data. You do not guess. You do not skip sections. You report what the tools return and reason over it.

---

## Hard Gates

Complete each gate in order. Do not advance past a failed gate.

1. **Tool Registry**
   - ✅ You have enumerated all wizard tools and all other MCP servers in this session
   - 🛑 If not: enumerate now, before calling any tool. List wizard tools first, then other MCPs grouped by provider. Hold this as your **Tool Registry** — you will reference it before answering any factual question, and save it at `session_end`.

---

## Steps

### Step 0 — Pre-populate wizard from available MCPs (conditional)

**Run this step if `open_tasks` is empty OR if you want a fresh sync.**

If `wizard_context` is null: inform the user no knowledge store is configured.
Run `wizard configure --knowledge-store` to set one up.

**If Atlassian MCP is available and `wizard_context` is not null:**
Call your Jira MCP to fetch open issues:
- For each issue, call `wizard:create_task`:
  - `name`: issue summary
  - `priority`: Highest/High → "high", Medium → "medium", Low/Lowest → "low"
  - `source_id`: issue key (e.g., "ENG-123")
  - `source_type`: "JIRA"
  - `source_url`: browse URL

**If Notion MCP is available and `wizard_context.tasks_db_id` is set:**
Query the tasks database using Notion MCP.
For each open task, call `wizard:create_task`:
  - `source_id`: Notion page ID
  - `source_type`: "NOTION"

**For Linear, Monday, or other MCPs:** follow the same pattern.

`wizard:create_task` deduplicates by `source_id` — safe to call every session.

### Step 1 — Build Tool Registry and Fetch Wizard Schemas

Before calling any tool:

- **Fetch all wizard tool schemas** by calling `ToolSearch` with `"select:mcp__wizard__session_start,mcp__wizard__session_end,mcp__wizard__task_start,mcp__wizard__save_note,mcp__wizard__create_task,mcp__wizard__update_task,mcp__wizard__get_tasks,mcp__wizard__get_task,mcp__wizard__resume_session,mcp__wizard__rewind_task,mcp__wizard__what_am_i_missing,mcp__wizard__get_meeting,mcp__wizard__save_meeting_summary,mcp__wizard__ingest_meeting,mcp__wizard__get_sessions,mcp__wizard__get_session,mcp__wizard__what_should_i_work_on,mcp__wizard__get_modes,mcp__wizard__set_mode"`. This pre-fetches all schemas so tools are callable throughout the session without additional ToolSearch calls.
- **List all other MCP servers** grouped by provider, noting what each does and when to prefer it over internal knowledge
- **Hold this registry in context** — reference it every time you would otherwise answer from memory

> **Hard rule:** Before answering any question about a library, API, or this codebase — stop and use a tool. Internal knowledge is the last resort, not the first.

### Step 2 — Call `session_start`

Call `session_start`. If the session boot context contains `agent_session_id=<value>`, pass it as the `agent_session_id` parameter. Example context: `agent_session_id=a8f3bc12-... source=startup. Begin this session by calling the wizard:session_start MCP tool.`

```python
# If additionalContext contains agent_session_id=<uuid>:
session_start(agent_session_id="a8f3bc12-...")

# If no agent_session_id in context (older hook or direct call):
session_start()
```

The `source` value in the response indicates the session type:
- `"startup"` — fresh session
- `"compact"` — continuation of a compacted session (`continued_from_id` will be set)
- `"resume"` — user explicitly resumed a prior session
