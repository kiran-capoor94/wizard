---
description: Code review using wizard context — surface prior investigations and decisions before reviewing changes
---

# Code Review

Use when reviewing code changes for a task.

## Steps

1. Call `task_start` to load prior context for the task
2. Read prior investigation and decision notes — understand what was already explored
3. Review the code changes with this lens (in order):
   - **Correctness** — does it do what it says? Are error paths handled?
   - **Blast radius** — what does this touch that was not intended?
   - **Invariant violations** — does it break SRP, DRY, or dependency rules?
   - **Observability** — can you debug this at 2am with structured logs?
   - **Tests** — do they verify behaviour, not just execute code paths?
   - **Simplicity** — is this the simplest thing that works?
4. Save review findings as a note (`note_type: investigation`) so the review context survives across sessions
5. Update task status if appropriate
