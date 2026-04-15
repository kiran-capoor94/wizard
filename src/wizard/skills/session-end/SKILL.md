# Session End

Use this skill at the end of every work session to save a structured summary and close the session cleanly.

## What this does

- Collects six structured fields from the engineer, then adds the tool_registry from session context
- Calls `session_end` with all nine parameters
- Persists a `SessionState` JSON object to the session record
- Writes the session summary to the Notion daily page
- Clears the session context so the next session starts clean

## Steps

**1. Ask the engineer for a session summary.** One or two sentences covering what was done.

**2. Collect the six structured fields.**

Ask each in turn (you may batch them if the engineer is terse):

- **intent**: What was the primary goal of this session? (One sentence.)
- **working_set**: Which task IDs were actively worked on? (List of integers from `session_start` output.)
- **state_delta**: What changed since the last session? (One sentence — status changes, blockers resolved, new discoveries.)
- **open_loops**: What's unresolved and needs follow-up? (List of strings, or empty list.)
- **next_actions**: What are the concrete next steps? (List of strings, or empty list.)
- **closure_status**: How did the session end? One of: `clean` (finished what was planned), `interrupted` (cut short), `blocked` (stuck on something).

**3. Call session_end with all nine parameters:**

```python
session_end(
    session_id=<from session_start>,
    summary="<summary>",
    intent="<intent>",
    working_set=[<task_id>, ...],
    state_delta="<state_delta>",
    open_loops=["<loop>", ...],
    next_actions=["<action>", ...],
    closure_status="<clean|interrupted|blocked>",
    tool_registry="<your Tool Registry from Step 0 of session-start>",
)
```

Pass the full Tool Registry text you built at session start. If you updated it during the session, pass the current version. If you no longer have it, pass `None`.

**4. Surface the confirmation.** The response includes echo fields — show the engineer:

- Session ID closed
- Closure status
- Number of open loops and next actions
- Whether Notion write-back succeeded

## Notes

- `working_set` is task IDs (integers), not task names.
- `open_loops` and `next_actions` can be empty lists — do not prompt unnecessarily.
- If the engineer is in a hurry, `closure_status="interrupted"` is fine and `open_loops`/`next_actions` can be `[]`.
- The `summary` field is scrubbed for PII before storage. The six structured fields are stored as-is in `session_state` JSON — remind the engineer not to include real names, emails, or patient data in open_loops/next_actions.
