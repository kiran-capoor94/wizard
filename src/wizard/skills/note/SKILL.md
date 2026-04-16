---
description: Save a reasoning artifact — investigation findings, decisions, documentation, or learnings anchored to a task
---

# Save Note

> **Tool check** — Before looking anything up to add to this note: consult your Tool Registry from this session. Wizard tools first, then other MCPs. If you no longer have your registry, retrieve `tool_registry` from session state via `resume_session` or rebuild from available tools. Internal knowledge is the last resort.

Use after any investigation, decision, or learning worth preserving across sessions.

## When to save

- After investigating a bug or system behaviour
- After making an architectural or design decision
- After documenting how something works
- After learning something non-obvious that will help next session

## How

Call `save_note` with:
- `task_id` — the task this note belongs to (required — every note is anchored to a task)
- `note_type` — one of: `investigation`, `decision`, `docs`, `learnings`
- `content` — the reasoning to preserve. Be specific. Include file paths, function names, error messages, and conclusions. Future sessions will read this cold.

## Note types

- **investigation** — what you looked at, what you found, what you ruled out
- **decision** — what was decided and why, including rejected alternatives
- **docs** — how something works, for reference
- **learnings** — surprising findings, gotchas, things to watch out for
