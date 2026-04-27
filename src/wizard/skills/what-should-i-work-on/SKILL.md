---
name: what-should-i-work-on
description: Use when the user asks what to work on, what's next, mentions available time, or wants a quick win. Infers mode and time_budget from user language, calls what_should_i_work_on, and presents the result as a direct recommendation.
---

# What Should I Work On

## When to use

Trigger this skill when the user says:
- "what should I work on?"
- "what's next?" / "what do I tackle next?"
- "I have 30 minutes" / "I've got an hour" / "rest of the day"
- "quick win" / "something easy" / "I'm back"
- "what's blocked?" / "what's stuck?"

## Step 0 — Fetch Tool Schemas (if not already loaded)

If wizard tool schemas haven't been fetched yet in this session, call `ToolSearch` with `"select:mcp__wizard__what_should_i_work_on,mcp__wizard__task_start,mcp__wizard__session_start"` before proceeding.

## Step 1 — Infer parameters

Before calling the tool, map the user's language to params:

**`time_budget`:**
- "30 min" / "30 minutes" / "half an hour" → `"30m"`
- "an hour" / "couple hours" / "2h" → `"2h"`
- "rest of the day" / "afternoon" / "few hours" → `"half-day"`
- "all day" / "full day" / "whole day" → `"full-day"`
- No time mention → omit (pass `None`)

**`mode`:**
- "quick win" / "something easy" / "low effort" / "small task" → `"quick-wins"`
- "what's blocked" / "what's stuck" / "unblock" → `"unblock"`
- Everything else → `"focus"` (default)

## Step 2 — Call the tool

```
wizard:what_should_i_work_on(
    session_id=<current session id>,
    mode=<inferred>,
    time_budget=<inferred or None>,
)
```

If you don't have a session_id, call `wizard:session_start` first.

## Step 3 — Present the result

**If `recommended_task` is null:**
> "No open tasks at the moment. Want to create one or check session_start for context?"

**If there's a recommendation:**
Present as a direct statement — not a table, not a list:

> "Work on **[name]** — [reason]
>
> Want me to start it?"

Then show alternatives on one compact line:
> Alternatives: **[name]** (active) · **[name]** (new) · **[name]** (cooling)

If `skipped_blocked > 0`:
> _(+{skipped_blocked} blocked task(s) skipped — use mode="unblock" to surface them)_

## Step 4 — On user response

**"Yes" / "start it" / confirmation:** Call `wizard:task_start(task_id=<recommended_task.task_id>)`.

**"Not that one" / "something else":** Offer the first alternative:
> "Next up: **[alternatives[0].name]** — [alternatives[0].reason]. Start this one?"

**"Give me a quick win":** Re-call with `mode="quick-wins"` if mode wasn't already set.

## Rules

- Do not re-reason over the data — trust the tool's ranking entirely.
- Do not ask the user to confirm time_budget or mode if you can infer them — just call the tool.
- Do not show scores or raw signal values to the user.
