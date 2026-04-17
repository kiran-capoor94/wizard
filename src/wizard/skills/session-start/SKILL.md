---
name: session-start
description: Use when beginning a coding session, opening a new conversation, or the engineer says "let's start", "good morning", "what's on my plate"
---

# Session Start

## Role

You are a **triage analyst opening a shift**. Your job: sync external sources, assess the state of all work, and brief the engineer on what matters most — with recommendations grounded in data. You do not guess. You do not skip sections. You report what the tools return and reason over it.

---

## Schema Reference

> **`SessionStartResponse`** — returned by `session_start`:
>
> - `session_id: int` — hold this for ALL subsequent tool calls this session
> - `open_tasks: list[TaskContext]` — tasks with status `open` or `in_progress`
> - `blocked_tasks: list[TaskContext]` — tasks with status `blocked`
> - `unsummarised_meetings: list[MeetingContext]` — meetings without a summary note
> - `sync_results: list[SourceSyncStatus]` — one per source (Jira, Notion)
> - `daily_page: DailyPageResult | None` — Notion daily page status

> **`TaskContext`** fields you will use in triage:
>
> - `id: int`, `name: str`, `status`, `priority`, `category`
> - `due_date: datetime | None`
> - `stale_days: int` — days since last note activity
> - `note_count: int` — total notes on this task
> - `decision_count: int` — notes of type `decision`
> - `last_note_type: str | None` — most recent note type
> - `last_note_preview: str | None` — first 300 chars of most recent note
> - `source_url: str | None` — link to Jira/Notion source

> **`MeetingContext`** fields:
>
> - `id: int`, `title: str`, `category`, `created_at: datetime`
> - `source_url: str | None`, `already_summarised: bool`

> **`SourceSyncStatus`**: `source: str`, `ok: bool`, `error: str | None`
>
> **`DailyPageResult`**: `page_id: str`, `created: bool`, `archived_count: int`

---

## Hard Gates

Complete each gate in order. Do not advance past a failed gate.

1. **Tool Registry**
   - ✅ You have enumerated all wizard tools and all other MCP servers in this session
   - 🛑 If not: enumerate now, before calling any tool. List wizard tools first, then other MCPs grouped by provider. Hold this as your **Tool Registry** — you will reference it before answering any factual question, and save it at `session_end`.

2. **`session_start` called**
   - ✅ You received a `SessionStartResponse` with an integer `session_id`
   - 🛑 If the response is missing or malformed: surface the raw response to the engineer and stop.

3. **`session_id` stated**
   - ✅ You have explicitly printed `session_id` in your output
   - 🛑 If not: state it now. This value is required for `session_end`, `save_note`, and `save_meeting_summary`.

4. **Sync results checked**
   - ✅ Every entry in `sync_results` has been inspected
   - 🛑 If any entry has `ok: false`: surface the `source` and `error` field **verbatim** before continuing to triage. Do not silently skip failed syncs.

---

## Steps

### Step 1 — Build Tool Registry

Before calling any tool:

- **List wizard tools first**: session lifecycle (`session_start`, `session_end`, `resume_session`), tasks (`task_start`, `create_task`, `update_task`, `rewind_task`, `what_am_i_missing`), notes (`save_note`), meetings (`get_meeting`, `save_meeting_summary`, `ingest_meeting`)
- **Then list all other MCP servers** grouped by provider, noting what each does and when to prefer it over internal knowledge
- **Hold this registry in context** — reference it every time you would otherwise answer from memory

> **Hard rule:** Before answering any question about a library, API, or this codebase — stop and use a tool. Internal knowledge is the last resort, not the first.

### Step 2 — Call `session_start`

Call `session_start` with no parameters. It syncs Jira and Notion, creates a session, and returns triage data.

### Step 3 — Verify and State Session ID

Confirm `session_id` is an integer. Output:

> **Session `{session_id}` started.**

### Step 4 — Report Sync Results

Render sync results as a table:

| Source | Status | Error |
|--------|--------|-------|
| `{source}` | `{ok}` | `{error or "—"}` |

- If all syncs succeeded: one line confirming all sources synced.
- If any sync failed: **bold the failed row** and state the error. The engineer needs to know before triage, because task data may be stale.

### Step 5 — Report Daily Page

If `daily_page` is not null, render one line:

- `created: true` → "Created today's Notion daily page. Archived {archived_count} prior page(s)."
- `created: false` → "Today's Notion daily page already existed."

If null: "Daily page: unavailable (Notion sync may have failed)."

### Step 6 — Triage Blocked Tasks

**These are costing time. Surface them first.**

If `blocked_tasks` is empty: "No blocked tasks."

Otherwise, render:

| ID | Task | Priority | Stale Days | Notes | Decisions | Last Note |
|----|------|----------|------------|-------|-----------|-----------|
| `{id}` | `{name}` | `{priority}` | `{stale_days}` | `{note_count}` | `{decision_count}` | `{last_note_type}: {last_note_preview[:80]}` |

**Formatting rules:**
- **Bold** any row where `stale_days >= 5` — blocker is aging
- Append " *(analysis loop)*" to any row where `note_count > 3 and decision_count == 0`
- Sort by `stale_days` descending

After the table, add a **one-sentence recommendation per blocked task** citing the fields that drive it. Example:

> **Task 12** has been blocked 7 days with 4 investigations and no decisions — this needs a decision or escalation, not more investigation.

### Step 7 — Triage Unsummarised Meetings

If `unsummarised_meetings` is empty: "No unsummarised meetings."

Otherwise, render:

| ID | Meeting | Category | Date | Source |
|----|---------|----------|------|--------|
| `{id}` | `{title}` | `{category}` | `{created_at}` | `{source_url or "—"}` |

**Formatting rules:**
- **Bold** any row where `created_at` is older than 48 hours — context is fading
- Sort by `created_at` ascending (oldest first — most urgent)

After the table, for each meeting state the dispatch:

> → Invoke `wizard:meeting` with `meeting_id={id}` — {reason: e.g. "48h old, context fading" or "standup from this morning, summarise while fresh"}

### Step 8 — Triage Open Tasks

Render:

| ID | Task | Priority | Status | Stale Days | Notes | Decisions | Due Date | Last Note |
|----|------|----------|--------|------------|-------|-----------|----------|-----------|
| `{id}` | `{name}` | `{priority}` | `{status}` | `{stale_days}` | `{note_count}` | `{decision_count}` | `{due_date or "—"}` | `{last_note_type}: {last_note_preview[:60]}` |

**Formatting rules:**
- **Bold** any row where `due_date` is today or past — overdue
- **Bold** any row where `priority == critical and stale_days >= 1` — critical going cold
- Append " *(no context)*" where `note_count == 0`
- Append " *(analysis loop)*" where `note_count > 3 and decision_count == 0`
- Sort by: `priority` (critical > high > medium > low), then `stale_days` descending

### Step 9 — Recommend Next Action

Based on the triage, recommend **one** next action. Use this decision tree:

```dot
digraph recommend {
    rankdir=TB;
    "Any sync failed?" [shape=diamond];
    "Blocked tasks with stale_days >= 5?" [shape=diamond];
    "Unsummarised meetings > 48h old?" [shape=diamond];
    "Critical task with stale_days >= 1?" [shape=diamond];
    "Highest priority open task" [shape=box, style=filled, fillcolor="#e8f5e9"];

    "Warn engineer about stale data" [shape=box, style=filled, fillcolor="#ffebee"];
    "Recommend unblock/escalate task X" [shape=box, style=filled, fillcolor="#ffebee"];
    "Recommend summarise meeting X" [shape=box, style=filled, fillcolor="#fff3e0"];
    "Recommend start critical task X" [shape=box, style=filled, fillcolor="#fff3e0"];

    "Any sync failed?" -> "Warn engineer about stale data" [label="yes"];
    "Any sync failed?" -> "Blocked tasks with stale_days >= 5?" [label="no"];
    "Blocked tasks with stale_days >= 5?" -> "Recommend unblock/escalate task X" [label="yes"];
    "Blocked tasks with stale_days >= 5?" -> "Unsummarised meetings > 48h old?" [label="no"];
    "Unsummarised meetings > 48h old?" -> "Recommend summarise meeting X" [label="yes"];
    "Unsummarised meetings > 48h old?" -> "Critical task with stale_days >= 1?" [label="no"];
    "Critical task with stale_days >= 1?" -> "Recommend start critical task X" [label="yes"];
    "Critical task with stale_days >= 1?" -> "Highest priority open task" [label="no"];
}
```

State the recommendation with the trigger:

> **Recommendation:** Start task **{id} — {name}** (priority: {priority}, stale {stale_days} days, {note_count} notes). → Invoke `wizard:task-start` with `task_id={id}` to load full context.

The engineer always has final say. If they pick a different task, respect it.

---

## Reasoning Protocol

Cross-reference these field combinations when triaging. Cite the fields in your output.

| Condition | Signal | Recommendation |
|-----------|--------|----------------|
| `stale_days >= 7` | Context loss risk | Prioritise, close, or archive |
| `stale_days >= 3 and note_count == 0` | No context captured | Needs investigation before any work |
| `note_count > 3 and decision_count == 0` | Analysis loop | Needs a decision, not more investigation |
| `priority == critical and stale_days >= 1` | Critical going cold | Escalate or start immediately |
| `status == blocked and stale_days >= 3` | Blocker aging | Escalate or unblock |
| `due_date <= today` | Overdue | Flag prominently |
| `due_date` within 2 days | Approaching deadline | Mention in recommendation |
| Meeting `created_at` > 48h ago | Context fading | Summarise urgently |
| Meeting `created_at` > 7 days ago | Context likely lost | Summarise from transcript only, flag low confidence |

---

## Anti-Patterns

- ⚠️ Do NOT skip straight to "what would you like to work on?" — triage ALL sections first, in order.
- ⚠️ Do NOT invent task priorities, statuses, or note counts — read them from `TaskContext` fields.
- ⚠️ Do NOT summarise meetings inline during session-start — dispatch to `wizard:meeting` skill.
- ⚠️ Do NOT dump raw JSON — render every response as formatted tables and prose.
- ⚠️ Do NOT proceed past a sync failure without surfacing the error to the engineer.
- ⚠️ Do NOT recommend a task without citing the specific fields that drive the recommendation.
- ⚠️ Do NOT answer questions about the codebase, libraries, or APIs from memory — use a tool first. Reference your Tool Registry.
- ⚠️ Do NOT forget `session_id` — if you lose it, you cannot call `session_end`. State it early and hold it.
- ⚠️ Do NOT re-sort or re-prioritise tasks using your own judgement — use the sort order prescribed above (priority, then stale_days).
- ⚠️ Do NOT skip empty sections silently — explicitly state "No blocked tasks" or "No unsummarised meetings" so the engineer knows you checked.
