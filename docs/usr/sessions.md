# Sessions

A session is a bounded work period. Wizard tracks what you worked on during a session, what decisions you made, which tasks you touched, and what you planned to do next — so the following session can start with that context already loaded.

## How sessions start

Sessions start automatically. When you open Claude Code (or any registered agent), the `SessionStart` hook fires and calls `wizard:session_start` before your first message. You don't need to do anything.

## What you get at session start

When a session starts, wizard loads:

- **Open tasks** — up to 20 non-blocked tasks, sorted by relevance
- **Blocked tasks** — all tasks currently marked as blocked
- **Prior session summaries** — the 3 most recent closed sessions, including what was worked on and what was left open
- **Active mode** — the skill mode configured for this session (if any)
- **Unsummarised meetings** — any meetings that don't yet have a summary note attached

This context is passed to your agent at the start of the conversation, so it already knows what you've been doing and what's waiting for you.

## Session continuity

If your previous session wasn't cleanly ended — for example, you closed your terminal without calling `session_end` — wizard detects the abandoned session and closes it automatically with a synthetic summary before starting your new session. The synthetic summary notes how many notes were saved and which tasks were touched, so the context isn't completely lost.

The prior session summaries that load at startup include these auto-closed sessions, so even if the previous session ended abruptly, the next one picks up the thread.

## How to end a session cleanly

Always end a session by calling `wizard:session_end`. Pass a summary of what you did, your intent, the tasks you touched, any open threads, and what you plan to do next.

A clean session end saves all of this structured state and makes it available at the start of your next session. It also triggers full synthesis of the transcript (if synthesis is enabled), which extracts notes from the entire conversation.

A session that isn't ended cleanly is handled by the auto-close mechanism, but the resulting summary is minimal — it's better to end sessions properly.

## What happens if you forget

Wizard's `SessionCloser` runs at every `session_start` and looks for abandoned sessions — sessions with no summary and no explicit close. It auto-closes any session created within the last 2 hours before the new session starts. Sessions older than 2 hours are closed in the background.

The auto-close summary looks like: "Auto-closed: 5 note(s) across 2 task(s). Last activity: 2026-05-01T14:32:00."

You won't lose notes that were saved during the session. The auto-close just records the session state based on what notes exist.

## How to resume a prior session

If you want to explicitly continue working on what you were doing in a previous session, call `wizard:resume_session` with the session ID:

```
wizard:resume_session { "session_id": 42 }
```

This creates a new session linked to the prior one and loads the full session state — the tasks you were working on, the notes from that session, any open threads, and what you planned to do next. It's the highest-fidelity way to pick up exactly where you left off.

If you don't specify a session ID, `resume_session` finds the most recent session that has notes.

## Prior summaries

The 3 most recent closed sessions are surfaced at every session start, regardless of whether you're resuming explicitly. Each summary includes the session ID, what was done, when it closed, and which tasks were touched. This means even in a fresh session, your agent has enough context to understand recent history without you having to re-explain it.
