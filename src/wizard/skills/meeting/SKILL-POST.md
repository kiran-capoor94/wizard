# Meeting Summarisation — Post-Call Guidance

## Schema Reference

> **`get_meeting` parameters:**
>
> - `meeting_id: int`

> **`GetMeetingResponse`** — returned:
>
> - `title: str`, `content: str` — the transcript/notes
> - `open_tasks: list[TaskContext]` — tasks linked to or mentioning this meeting
> - `already_summarised: bool` — whether a summary note already exists

> **`save_meeting_summary` parameters:**
>
> - `meeting_id: int`
> - `session_id: int` — from `session_start`
> - `summary: str` — the structured summary you write
> - `task_ids: list[int]` — related wizard task IDs (optional)

> **`SaveMeetingSummaryResponse`** — returned:
>
> - `note_id: int`, `tasks_linked: int`

> **`ingest_meeting` parameters** (for new meetings):
>
> - `title: str`, `content: str` — transcript text
> - `source_url: str | None`, `category: str | None`

> **`IngestMeetingResponse`** — returned:
>
> - `meeting_id: int`, `already_existed: bool`

---

## Hard Gates

2. **Meeting loaded**
   - ✅ You called `get_meeting` and received a response with `content`
   - 🛑 If content is empty or very short (< 50 chars): flag to the engineer — transcript may be missing or incomplete. Do not fabricate a summary.

3. **Not already summarised**
   - ✅ `already_summarised == false`
   - 🛑 If `already_summarised == true`: tell the engineer and ask if they want to re-summarise or skip. Do not silently overwrite.

4. **Summary is grounded in transcript**
   - ✅ Every decision, action item, and fact in your summary can be traced to specific text in `content`
   - 🛑 If you cannot find support in the transcript for a claim: do not include it. Mark gaps explicitly.

---

## Steps

### Step 2 — Check Already Summarised

If `already_summarised == true`:

> Meeting **{meeting_id} — {title}** is already summarised. Skip, or re-summarise?

Wait for the engineer's response. Do not proceed without confirmation.

### Step 3 — Assess Transcript Quality

Before analysing, check the transcript:

- **Length**: If `content` is < 50 characters → flag as possibly incomplete
- **Structure**: Is it a raw transcript, AI-generated notes, or meeting minutes?
- **Age**: Compare meeting date to now. If > 7 days old, flag reduced confidence:
  > ⚠️ This meeting is {n} days old. Summary confidence may be lower for implicit context.

### Step 4 — Review Linked Tasks

Check `open_tasks` returned by `get_meeting`. These are wizard tasks already associated with or mentioning this meeting. Hold them as context — decisions and action items may relate to these tasks.

### Step 5 — Analyse Transcript

Read the full transcript. Extract four categories:

**5A — Key Decisions**
- What was agreed, and by whom (if attributable)
- Only include explicit decisions stated in the transcript
- If something sounds like a decision but is ambiguous, mark it: "*(tentative — not explicitly confirmed)*"

**5B — Action Items**
- Who does what, with deadlines if stated
- Cross-reference with `open_tasks`: if an action item matches an existing wizard task, note the task ID
- If an action item has no matching task: flag it for potential `create_task`

**5C — Open Questions**
- Items discussed but not resolved
- Items where someone said "let's follow up" or "we need to check"

**5D — Task Links**
- Wizard task IDs discussed or relevant
- From `open_tasks` that were mentioned in the transcript
- From action items that map to existing tasks

### Step 6 — Write the Summary

Use this structure:

```
## Key Decisions
- {decision 1} — {who decided, if known}
- {decision 2}

## Action Items
- [ ] {action} — {owner, if known} {(wizard task #{id})}
- [ ] {action} — {owner} *(no matching task — consider creating)*

## Open Questions
- {question 1} — {context}
- {question 2}

## Related Tasks
- Task #{id} — {name}: {how it relates}
```

If any section is empty, include it with "None identified."

### Step 7 — Present Summary for Review

Show the summary to the engineer before saving:

> **Meeting {meeting_id} — {title}** summary:
>
> {rendered summary}
>
> **Task IDs to link:** {list or "none"}
>
> Save this summary?

### Step 8 — Call `save_meeting_summary`

After engineer confirms:

```
save_meeting_summary(
    meeting_id={id},
    session_id={session_id},
    summary="{summary}",
    task_ids=[{ids}],
)
```

### Step 9 — Confirm and Report

> Meeting **{title}** summarised.
>
> | | |
> |---|---|
> | Note | #{note_id} |
> | Tasks linked | {tasks_linked} |

If any action items had no matching wizard task, prompt:

> {n} action item(s) have no matching wizard task. Create tasks for them?
> - {action item 1} → `create_task`?
> - {action item 2} → `create_task`?

---

## Ingesting New Meetings

When the engineer pastes a transcript or references a meeting not yet in wizard:

1. Call `ingest_meeting` with `title`, `content`, `source_url` (if available), and `category`
2. Check `already_existed` — if true, the meeting was already ingested. Use the returned `meeting_id`.
3. Proceed to Step 1 (load and summarise) using the returned `meeting_id`.

---

## Anti-Patterns

- ⚠️ Do NOT fabricate decisions or action items not in the transcript — if it's not there, it doesn't go in the summary.
- ⚠️ Do NOT silently overwrite an existing summary — check `already_summarised` and ask first.
- ⚠️ Do NOT save the summary without showing it to the engineer — they may want to correct attributions or add context.
- ⚠️ Do NOT skip the task-linking step — connecting meetings to tasks is how wizard builds cross-session context.
- ⚠️ Do NOT ignore old meeting age — flag reduced confidence for meetings > 7 days old.
- ⚠️ Do NOT leave action items with "no matching task" unreported — prompt the engineer to create tasks.
- ⚠️ Do NOT attribute decisions to specific people unless the transcript clearly names them.
- ⚠️ Do NOT include empty sections silently — explicitly state "None identified" so the engineer knows you checked.
