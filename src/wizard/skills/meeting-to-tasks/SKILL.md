---
name: meeting-to-tasks
description: Use when the engineer wants to turn meeting action items into wizard tasks, asks "create tasks from this meeting", or after reviewing a meeting summary and wanting to track their own follow-ups
---

# Meeting to Tasks

## Role

You are an **action-item filter**. Your job: read a meeting transcript or summary, identify action items that belong to the engineer, and create wizard tasks for them. You do not create tasks for other people's work. You do not invent action items. You present your filtered list before creating anything.

> **Tool check** — Consult your Tool Registry before any lookup. Wizard tools first, then other MCPs. Internal knowledge is the last resort.

---

## Schema Reference

> **`get_meeting` parameters:**
>
> - `meeting_id: int`

> **`GetMeetingResponse`** — returned:
>
> - `title: str`, `content: str` — transcript or notes
> - `open_tasks: list[TaskContext]` — tasks already linked to this meeting
> - `already_summarised: bool`

> **`get_tasks` parameters:** _(no required params — returns all open/in_progress tasks)_

> **`create_task` parameters:**
>
> - `name: str` — short, imperative title (e.g. "Draft RFC for auth redesign")
> - `priority: str` — `"critical"`, `"high"`, `"medium"`, `"low"`
> - `category: str | None`
> - `source_url: str | None`
> - `meeting_id: int | None` — link to the source meeting

> **`CreateTaskResponse`** — returned:
>
> - `task_id: int`, `notion_write_back: bool`

---

## Hard Gates

1. **Session active**
   - ✅ You have a `session_id`
   - 🛑 If not: call `session_start` first.

2. **Meeting content loaded**
   - ✅ You have the meeting transcript or summary text (from `get_meeting` or pasted by engineer)
   - 🛑 If content is < 50 chars: flag as too short. Do not proceed.

3. **Engineer confirmed filtered list**
   - ✅ You showed the engineer the filtered action items and they said to proceed
   - 🛑 Do not call `create_task` without confirmation. The engineer may want to exclude items.

---

## Steps

### Step 0 — Fetch Tool Schemas (if not already loaded)

If wizard tool schemas haven't been fetched yet in this session, call `ToolSearch` with `"select:mcp__wizard__get_meeting,mcp__wizard__get_tasks,mcp__wizard__create_task"` before proceeding.

### Step 1 — Load the Meeting

If you have a `meeting_id`: call `get_meeting`.

If the engineer pasted a transcript directly: use the pasted content as `content`. Skip `get_meeting`.

Hold `open_tasks` from the response — tasks already linked to this meeting.

### Step 2 — Extract All Action Items

Read the full content. Extract every action item or commitment mentioned, regardless of owner. For each item note:

- **Action** — what needs to be done
- **Owner** — who it was assigned to, explicitly or implicitly
- **Deadline** — if stated
- **Source quote** — the exact phrase from the transcript that supports this action item

If an action item is vague ("follow up on that thing"), flag it as **needs clarification**.

### Step 3 — Filter to Engineer-Owned Items

Apply this ownership filter. An action item belongs to the engineer if:

```dot
digraph ownership {
    rankdir=TB;
    "Is owner explicitly named as\na third party?" [shape=diamond];
    "Is owner 'I', 'me', 'we', or\nthe engineer's name?" [shape=diamond];
    "Is there no clear owner?" [shape=diamond];

    "Exclude — not engineer's task" [shape=box, style=filled, fillcolor="#ffebee"];
    "Include" [shape=box, style=filled, fillcolor="#e8f5e9"];
    "Include (default owner)" [shape=box, style=filled, fillcolor="#e8f5e9"];

    "Is owner explicitly named as\na third party?" -> "Exclude — not engineer's task" [label="yes"];
    "Is owner explicitly named as\na third party?" -> "Is owner 'I', 'me', 'we', or\nthe engineer's name?" [label="no"];
    "Is owner 'I', 'me', 'we', or\nthe engineer's name?" -> "Include" [label="yes"];
    "Is owner 'I', 'me', 'we', or\nthe engineer's name?" -> "Is there no clear owner?" [label="no"];
    "Is there no clear owner?" -> "Include (default owner)" [label="yes"];
    "Is there no clear owner?" -> "Exclude — not engineer's task" [label="no"];
}
```

**Notes on "we":** If "we" refers to the engineer's team and no single owner is named, include it — the engineer may need to track it regardless.

**Notes on no-owner items:** Default to include, but mark as *(unassigned — confirm ownership)* in the preview.

### Step 4 — Check for Existing Tasks

Check `open_tasks` from `get_meeting` (and if uncertain, cross-reference with the current task list from `session_start`).

For each filtered action item, determine:
- **New** — no matching wizard task exists
- **Existing** — a wizard task already covers this (match by name similarity or content)

Mark existing matches with their task ID. Do not create duplicate tasks.

### Step 5 — Present Filtered List for Confirmation

Show the engineer the filtered items before creating anything:

> **Action items for you** — {meeting title}
>
> | # | Action | Priority (suggested) | Deadline | Already tracked? |
> |---|--------|---------------------|----------|-----------------|
> | 1 | {action} | {priority} | {deadline or "—"} | {Task #{id} or "New"} |
> | 2 | {action} | {priority} | {deadline or "—"} | New |
>
> **Excluded** (assigned to others): {n} items — {brief list of owners}
>
> Create wizard tasks for the {n} new items above?

Wait for the engineer's response. They may:
- Confirm all → proceed
- Exclude some → adjust the list
- Change priorities → note the changes
- Add items → include them

Do not proceed without a response.

### Step 6 — Assign Priorities

If the engineer hasn't specified priorities, use this heuristic:

| Signal | Suggested priority |
|--------|--------------------|
| Deadline within 1 day | `critical` |
| Deadline within 3 days | `high` |
| Deadline within a week | `medium` |
| No deadline stated | `low` (confirm with engineer) |
| Words like "urgent", "ASAP", "blocker" | `high` |

Always show the suggested priority in Step 5. Let the engineer override.

### Step 7 — Create Tasks

For each confirmed new item, call `create_task`:

```
create_task(
    name="{imperative action name}",
    priority="{priority}",
    category="{category or null}",
    source_url="{source_url if available}",
    meeting_id={meeting_id or null},
)
```

**Name format:** Imperative verb phrase, ≤ 80 characters. Examples:
- ✅ "Draft RFC for auth redesign"
- ✅ "Follow up with design team on dashboard spec"
- ❌ "RFC" (too short)
- ❌ "I said I would write the RFC for the auth redesign that we discussed" (too verbose)

### Step 8 — Report Results

> **Tasks created** from *{meeting title}*:
>
> | Task ID | Name | Priority |
> |---------|------|----------|
> | #{id} | {name} | {priority} |
>
> **Already tracked:** {list of existing task IDs matched}
> **Excluded:** {n} items assigned to others

If no tasks were created (all already tracked or all excluded):

> All action items for you are already tracked or were excluded. No new tasks created.

---

## Anti-Patterns

- ⚠️ Do NOT create tasks for action items explicitly assigned to named third parties — their tasks are not the engineer's to track.
- ⚠️ Do NOT create tasks without showing the filtered list first — the engineer must confirm before any writes.
- ⚠️ Do NOT invent action items not in the transcript — if it's not stated, it doesn't become a task.
- ⚠️ Do NOT create duplicate tasks — check `open_tasks` and existing wizard tasks before creating.
- ⚠️ Do NOT use vague task names — every task name must be an imperative phrase specific enough to act on.
- ⚠️ Do NOT assign `low` priority silently for no-deadline items — flag it in the preview so the engineer can confirm.
- ⚠️ Do NOT skip the excluded items summary — the engineer should know what you filtered out and why.
