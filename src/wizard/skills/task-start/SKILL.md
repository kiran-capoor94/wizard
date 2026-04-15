---
description: Start working on a task — loads prior notes and signals fresh start vs compounding session
---

# Task Start

> **Tool check** — Before any investigation, analysis, or knowledge lookup: consult your Tool Registry from this session. Wizard tools first, then other MCPs. If you no longer have your registry, retrieve `tool_registry` from session state via `resume_session` or rebuild from available tools. Internal knowledge is the last resort.

Run when the engineer selects a task to work on.

## Steps

1. Call `task_start` with the `task_id`
2. Check the `compounding` flag:
   - **true** — prior notes exist. Read them before touching code. Build on existing investigations and decisions. Do not re-discover what was already found.
   - **false** — fresh start. No prior context for this task.
3. Review `notes_by_type` for the shape of prior work (e.g. `{"investigation": 3, "decision": 1}`)
4. Read `prior_notes` from most recent to oldest
5. Begin investigation or implementation, saving findings with `wizard:note`
