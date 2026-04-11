---
description: Start working on a task — loads prior notes and signals fresh start vs compounding session
---

# Task Start

Run when the engineer selects a task to work on.

## Steps

1. Call `task_start` with the `task_id`
2. Check the `compounding` flag:
   - **true** — prior notes exist. Read them before touching code. Build on existing investigations and decisions. Do not re-discover what was already found.
   - **false** — fresh start. No prior context for this task.
3. Review `notes_by_type` for the shape of prior work (e.g. `{"investigation": 3, "decision": 1}`)
4. Read `prior_notes` from most recent to oldest
5. Begin investigation or implementation, saving findings with `wizard:note`
