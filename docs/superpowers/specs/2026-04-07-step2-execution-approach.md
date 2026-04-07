# Step 2 Execution Approach

**Date:** 2026-04-07
**Author:** Kiran Capoor
**Status:** Approved

## What This Is

This document captures the execution approach for Step 2 of the Wizard v2 build sequence. The implementation plan is already written at `docs/superpowers/plans/2026-04-04-wizard-v2-step2.md` and is fully aligned with SPEC_v8.md. This spec captures the execution cadence decision only.

## Context

Step 1 is complete as of commit `ec50fde`. The services layer (`services/`) and workflow definitions directory (`core/`) do not yet exist. Step 2 builds both.

Step 2 goal (from plan): Build the services layer — variable injection, pre-flight check, session lifecycle, and workflow execution — and prove the LLM layer is invoked with prepared context, pre-flight passes before invocation, and session state survives a simulated crash.

## Execution Cadence

**Option A — task-by-task with wizard-review after each commit.**

For each of the 8 plan tasks:
1. Run the task (TDD: failing test → implementation → passing test)
2. Commit as specified in the plan
3. Run `wizard-review` — if violations found, fix and re-commit before proceeding
4. Move to the next task

## Tasks

| # | Task | Output |
|---|------|--------|
| 1 | `tsconfig.json` — add `core/` to include | `core/workflows/` directory skeleton |
| 2 | `services/inject.ts` + migrate skill-injection test | Variable injection function |
| 3 | `services/preflight.ts` | Pre-flight check (Postgres + pgvector) |
| 4 | `services/session.ts` | Session lifecycle (create, end, attach, get) |
| 5 | `core/workflows/task-start.ts` + `services/workflow.ts` | Workflow execution |
| 6 | MCP tools update | `session_start`, `task_start`, `session_end` tools |
| 7 | `tests/contracts/services-to-llm.test.ts` | Step 2 contract proof |
| 8 | Final verification | All tests pass, zero TS errors, proof criteria met |

## Wizard-Review Checks

After each commit, `wizard-review` runs these checks against the diff:
- `wizard-check-boundaries` — no layer boundary violations
- `wizard-check-types` — no type contract drift
- `wizard-check-scope` — no out-of-scope components
- `wizard-check-step` — no future-step code
- `wizard-check-tests` — no empty/placeholder tests

Violations must be fixed before the next task begins.

## Success Criteria

- All 8 tasks complete with passing tests
- All wizard-review runs pass clean
- `yarn test`: 19+ tests passing (9 from Step 1 + 19 new)
- `tsc --noEmit`: zero errors
- Step 2 proof criteria met: pre-flight passes, workflow returns resolved prompt, session survives simulated crash
