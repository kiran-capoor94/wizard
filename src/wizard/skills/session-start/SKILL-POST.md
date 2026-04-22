# Session Start — Post-Call Guidance

## Schema Reference

**`SessionStartResponse`** key fields:
- `session_id: int` — hold for all subsequent tool calls this session
- `open_tasks: str` — TOON-encoded array of up to 20 open/in-progress tasks by priority + recency. Format: `open_tasks[N]{id,name,status,priority,category,due_date,stale_days,note_count,decision_count,last_note_type,last_note_preview (truncated to 80 chars),source_url}:` followed by one CSV row per task. Empty marker `open_tasks[0]` when none.
- `open_tasks_total: int` — total open task count (may exceed 20)
- `blocked_tasks: str` — TOON-encoded array of blocked tasks, same column schema as `open_tasks`.
- `unsummarised_meetings: list[MeetingContext]`
- `wizard_context: dict | None` — knowledge store addresses (`tasks_db_id`, `meetings_db_id`, `daily_parent_id` for Notion; `vault_path`, `daily_notes_folder`, `tasks_folder` for Obsidian)
- `closed_sessions: list[ClosedSessionSummary]` — sessions auto-closed this run (≤3, recent only)
- `prior_summaries: list[PriorSessionSummary]` — up to 3 most recent closed sessions with summaries, for prior-context loading

**`TaskContext`** key fields: `id`, `name`, `status`, `priority`, `category`, `due_date`, `stale_days`, `note_count`, `decision_count`, `last_note_type`, `last_note_preview` (300 chars), `source_url`

**`MeetingContext`** key fields: `id`, `title`, `category`, `created_at`, `source_url`, `already_summarised`

---

## Hard Gates (post-call)

Complete each gate in order. Do not advance past a failed gate.

2. **`session_start` called**
   - ✅ You received a `SessionStartResponse` with an integer `session_id`
   - 🛑 If the response is missing or malformed: surface the raw response to the engineer and stop.

3. **`session_id` stated**
   - ✅ You have explicitly printed `session_id` in your output
   - 🛑 If not: state it now. This value is required for `session_end`, `save_note`, and `save_meeting_summary`.

---

## Steps (post-call)

### Step 3 — Verify and State Session ID

Confirm `session_id` is an integer. Output:

> **Session `{session_id}` started.**

### Step 3b — Prior Context (conditional)

**Run this step only when `prior_summaries` is non-empty.**

Render a **Prior context** block before task triage so the engineer knows what was in flight:

| Session | Closed | Summary | Tasks |
|---------|--------|---------|-------|
| `{session_id}` | `{closed_at}` | `{summary[:200]}` | `{task_ids or "—"}` |

Sort by `closed_at` descending (most recent first). Truncate summary to 200 characters.

This is context loading — do not recommend actions based on prior summaries. Triage comes in Steps 4–7.

### Step 4 — Triage Blocked Tasks

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

### Step 5 — Triage Unsummarised Meetings

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

### Step 6 — Triage Open Tasks

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

### Step 7 — Recommend Next Action

Based on triage, recommend **one** next action using this priority order:

1. Any sync failed → warn engineer about stale data
2. Blocked task with `stale_days >= 5` → recommend unblock/escalate
3. Unsummarised meeting older than 48h → recommend summarise
4. Critical task with `stale_days >= 1` → recommend start immediately
5. Otherwise → highest priority open task by the sort order from Step 6

State the recommendation with the trigger:

> **Recommendation:** Start task **{id} — {name}** (priority: {priority}, stale {stale_days} days, {note_count} notes). → Call `task_start` with `task_id={id}` to load full context.

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

- ⚠️ Do NOT summarise meetings inline during session-start — dispatch to `wizard:meeting` skill.
- ⚠️ Do NOT recommend a task without citing the specific fields that drive the recommendation.
- ⚠️ Do NOT answer questions about the codebase, libraries, or APIs from memory — use a tool first. Reference your Tool Registry.
- ⚠️ Do NOT forget `session_id` — if you lose it, you cannot call `session_end`. State it early and hold it.
- ⚠️ Do NOT re-sort or re-prioritise tasks using your own judgement — use the sort order prescribed above (priority, then stale_days).
- ⚠️ Do NOT skip empty sections silently — explicitly state "No blocked tasks" or "No unsummarised meetings" so the engineer knows you checked.
