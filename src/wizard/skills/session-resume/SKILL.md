---
name: session-resume
description: Resume a prior Wizard session in a new LLM thread. Use when the engineer says "continue where I left off", "pick up from yesterday", "what was I working on", or opens a new thread mid-task.
---

## Step 1 — Call the tool

Call `resume_session` from the wizard MCP server.
If the engineer mentions a specific session, pass that `session_id`.
Otherwise call with no arguments — Wizard will find the most recent session with notes.

## Step 2 — Surface session_state first

If `session_state` is present, display it before anything else:

```
Resuming session [resumed_from_session_id]

Intent:  [intent]
Changed: [state_delta]
Open:    [open_loops as bullet list]
Next:    [next_actions as bullet list]
Status:  [closure_status]
```

If `session_state` is null, say:
```
Session [N] was not cleanly closed — no structured state available.
Falling back to note history.
```
Then show the `prior_notes` grouped by task.

## Step 2b — Restore Tool Registry

After Step 2 (whether session_state was present or null), restore your Tool Registry:

- If `session_state.tool_registry` is a non-empty string: restore it as your active Tool Registry for this session.
- If absent or null: rebuild the registry now by enumerating all available tools (wizard tools first, then all other MCP servers grouped by provider).

Hold the registry in context. You will save it again at `session_end`.

## Step 3 — Show working set tasks

Display the `working_set_tasks` table: ID | Task | Status | Priority

These are the tasks the session was focused on, with current state from Jira/Notion.

## Step 4 — Ask

"Which task do you want to continue?"

## Important

- Use the **NEW** `session_id` for all subsequent calls — not `resumed_from_session_id`.
- Sync has already run. The task list is current.
- Only work within the current repository directory.
