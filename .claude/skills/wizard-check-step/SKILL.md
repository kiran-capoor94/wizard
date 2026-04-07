---
name: wizard-check-step
description: >
  Use when you want to check for build sequence violations in the Wizard codebase. Detects code
  that belongs to a future build step when the current step isn't complete yet. Invoke with
  /wizard-check-step.
---

# Build Sequence Violation Detection

Check the Wizard codebase for code that belongs to a future build step. Wizard is built in 5 sequential steps — each proves a contract before the next adds complexity. Report findings in the format below.

## What To Check

### 1. Determine Current Step

Read `AGENTS.md` in the project root. Find the line matching `Current status: **Step N`. Extract the step number.

If the line is not found, report `SKIP — Cannot determine current step from AGENTS.md`.

### 2. Load Current Step's File Map

Read the implementation plan for the current step from `docs/superpowers/plans/`. The plans are named with the step number (e.g., `wizard-v2-step1.md`, `wizard-v2-step2.md`).

Extract the file map table — this lists every file that should be created or modified in the current step.

### 3. Check Changed Files Against Step Scope

Run `git diff --name-only` (staged + unstaged) to get the list of changed files.

For each changed file, check:

**Step boundaries — what belongs where:**

| Directory/File | Belongs to Step |
|---|---|
| `prisma/schema.prisma`, `data/`, `shared/types.ts`, `services/`, `llm/adapters/` (embedding), tests | Step 1 |
| `orchestrator/` (workflow execution, session lifecycle, pre-flight) | Step 2 |
| `integrations/` (first: Notion), `security/` (PII scrubbing), `wizard.config.yaml`, CLI setup | Step 3 |
| LLM output pipeline (process, transform, validate, store) in `llm/` or `services/` | Step 4 |
| Remaining `integrations/` (Jira, Krisp, Serena, GitHub), `cli/` (full commands), `evals/`, second LLM adapter | Step 5 |

If a changed file belongs to a step later than the current step, it is a FAIL.

### 4. Check Dependencies

Review `package.json` for newly added dependencies. Flag any that are only needed for a future step. For example:
- `@notionhq/client` before Step 3
- Sentry SDK before Step 3 (core/ owns Sentry config, built in Step 3)
- CLI framework (e.g., `commander`, `yargs`) before Step 5

### 5. Check Proof Criteria Alignment

Read the current step's proof criteria from the plan. Check whether the work being done contributes toward proving the current step, not a different step.

This is a judgement call — report concerns, not hard failures.

## Output Format

```
## Build Step Check (Current: Step 1)

### FAIL — Future step code (2 issues)
- orchestrator/session.ts — session lifecycle belongs to Step 2
- security/scrubber.ts — PII scrubbing belongs to Step 3

### PASS — No premature dependencies
### NOTE — Proof criteria alignment looks correct

Result: PASS / FAIL
```
