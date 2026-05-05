---
name: product-owner/sub-skills/acceptance-criteria
description: Define what 'done' looks like for a feature in observable, testable terms
disable-model-invocation: true
allowed-tools: mcp__wizard__task_start mcp__wizard__save_note mcp__wizard__update_task ToolSearch
---

# Acceptance Criteria

## Role

You define done. Not "implemented" — done. Done means a user can accomplish their goal, the behaviour is observable without reading code, and a test can verify it.

## Format

Every criterion follows Given/When/Then:
```
Given {a starting state}
When {the user does something}
Then {the observable outcome}
```

## Steps

### Step 0 — Fetch Wizard Tool Schemas

If wizard tool schemas are not already loaded, call `ToolSearch` to fetch the schemas for any wizard tools this skill uses before proceeding. Skip if session-start already ran this session.

### Step 1 — Load the task
Call `task_start` to get the task name, notes, and any prior criteria.

### Step 2 — Draft criteria
Write one criterion per distinct user behaviour the feature must support.

Rules:
- **Observable** — "the dashboard shows X" not "the code sets flag Y"
- **Testable** — a person (or automated test) can verify it without reading implementation
- **Specific** — "returns results in <200ms" not "performs well"
- **User-language** — describe what the user sees/does, not what the system does internally

### Step 3 — Add edge cases
For each happy-path criterion, add at least one failure case.

### Step 4 — Record on task
Save criteria as a `docs` note on the task.

## Anti-Patterns

- ⚠️ Do NOT write criteria in system-language ("the service returns 200") — write in user-language ("the user sees confirmation"), or the criteria cannot be verified by a non-engineer
- ⚠️ Do NOT skip failure cases — a feature that handles only the happy path is an incomplete feature that will fail users in predictable edge cases
- ⚠️ Do NOT write criteria that require reading code to verify — if it's not observable from the outside, it's not a criterion
