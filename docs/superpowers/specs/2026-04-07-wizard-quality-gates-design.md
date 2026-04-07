# Wizard Quality Gates — Claude Code Skills & Agent Design

**Date:** 2026-04-07
**Author:** Kiran Capoor
**Status:** Approved

---

## Problem

Claude Code sessions routinely introduce violations of Wizard's architecture invariants. The most damaging:

1. **PII bypass** — Raw integration data reaching Data/LLM layers without passing through Security
2. **Layer boundary violations** — Services calling Postgres directly, orchestrator interpreting semantic content, LLM layer reaching external systems
3. **Type contract drift** — Prisma enums re-declared instead of re-exported, `undefined` instead of `null`, string IDs instead of ints
4. **Build sequence violations** — Code from Steps 2–5 appearing while Step 1 is in progress
5. **Empty/placeholder tests** — Stubs (`it.todo()`, empty bodies, `toBeDefined()`-only assertions) that look like progress but assert nothing
6. **Out-of-scope implementations** — Removed components (queues, DLQ, hallucination detection, stubbing) and Section 16 exclusions appearing in code

These are caught manually today, which is slow and unreliable.

---

## Solution

Six individual Claude Code skills for on-demand spot checks, plus one orchestrating agent (`wizard-review`) that selects and runs the relevant skills based on what changed.

### Structure

```
.claude/skills/
├── wizard-check-pii/SKILL.md           # PII leak detection
├── wizard-check-boundaries/SKILL.md    # Layer boundary violations
├── wizard-check-types/SKILL.md         # Type contract drift
├── wizard-check-scope/SKILL.md         # Out-of-scope & removed components
├── wizard-check-tests/SKILL.md         # Empty/placeholder test detection
├── wizard-check-step/SKILL.md          # Build sequence violations

.claude/agents/
├── wizard-review.md                    # Runs relevant skills, consolidates report
```

Skills and agent are project-local (`.claude/` in repo root), not global (`~/.claude/`). This means they are version-controlled, portable across machines, and scoped to the Wizard project.

---

## Skills

### `/wizard-check-pii`

Detects PII bypass and PII in test data.

**Checks:**
- Direct imports from `integrations/` into `data/`, `services/`, `orchestrator/`, or `llm/` (bypasses Security layer)
- PII patterns in test fixtures and seed data: emails, phone numbers, NHS numbers, names in clinical-looking strings
- The dependency flow `Integration → Security → Data` is preserved

**Pass condition:** No direct integration-to-data imports. No PII patterns in test fixtures.

**References:** SPEC_v6 §3.1 (dependency flow), §3.3 Security Layer ("nothing containing PII ever reaches Postgres"), §16 ("stubbing — PII scrubbing only, not replacement").

---

### `/wizard-check-boundaries`

Detects layer responsibility violations.

**Checks:**
- Services importing `PrismaClient` or `@prisma/client` directly instead of calling repositories in `data/`
- Orchestrator interpreting semantic content (parsing meeting keyPoints, evaluating note content, etc.) — it controls flow only
- LLM layer (`llm/`) importing from `integrations/` or reaching external systems
- Business logic in `shared/` — must contain types and constants only
- Workflow definitions in `orchestrator/` instead of `core/`
- Context assembly logic in `orchestrator/` instead of `services/`
- `core/` importing from `orchestrator/` or `services/` (wrong dependency direction)

**Pass condition:** Import graph respects `Integration → Security → Data ← Orchestration → LLM Layer → Data`.

**References:** SPEC_v6 §3.1 (dependency flow), §3.3 (layer specifications), §4 (key distinctions).

---

### `/wizard-check-types`

Detects type contract drift from Prisma source of truth.

**Checks:**
- Prisma enums (`TaskStatus`, `TaskType`, `TaskPriority`, `SessionStatus`, `WorkflowStatus`, `NoteType`, `NoteParent`, `RepoProvider`) declared anywhere instead of re-exported from `shared/types.ts`
- `undefined` used where `| null` is required (Prisma convention)
- IDs typed as `string` instead of `number`
- `TaskContext` defined outside `shared/types.ts`
- Embedding dimensions other than `vector(768)` in schema, migrations, or code

**Pass condition:** Single source of truth for enums, correct nullability, correct ID types, correct embedding dimensions.

**References:** SPEC_v6 §3.3 Data Layer ("all embedding vectors are vector(768)"), AGENTS.md Code Style (types section).

---

### `/wizard-check-scope`

Detects removed components and out-of-scope implementations.

**Removed components (SPEC_v6 §11):**
- Queues, DLQ, or background job infrastructure
- Exaggeration detection
- Hallucination detection (attribution check via pgvector is distinct and allowed)
- Full eval framework (scaffold only in v2)
- Four code intelligence structures: LSP symbols, TreeSitter, call maps, inheritance graphs

**Out of scope (SPEC_v6 §16):**
- Hosting, cloud deployment, multi-tenancy infrastructure
- PII stubbing/replacement (scrub only)
- Dynamic workflow definitions (hardcoded only)
- Authentication/auth middleware (User model exists, auth deferred)
- Clinical data handling
- Semantic threshold auto-calibration
- Billing, licensing, commercial infrastructure
- LSP integration directly in Wizard (Serena provides the bridge)

**Pass condition:** No removed components. No out-of-scope items.

**Note:** Build step scope violations (code from future steps) are handled by `/wizard-check-step`, not this skill.

**References:** SPEC_v6 §11, §16.

---

### `/wizard-check-tests`

Detects empty, placeholder, and weak tests.

**Checks:**
- `it.todo()` or `test.todo()` calls
- Empty test bodies: `test('...', () => {})` or trivially true assertions (`expect(true).toBe(true)`)
- Weak-only assertions: `toBeDefined()`, `toBeTruthy()`, `not.toBeNull()` as the sole assertion in a test (fine if followed by specific field assertions)
- `describe` blocks with no `it`/`test` children
- Mock-heavy tests that mock the thing under test instead of asserting actual behavior

**Pass condition:** Every test file has substantive assertions that verify behavior, not existence.

**References:** AGENTS.md Testing section ("tests verify behaviour, not code paths").

---

### `/wizard-check-step`

Detects build sequence violations.

**Checks:**
- Reads current step from AGENTS.md (`Current status: Step N in progress`)
- Cross-references changed files against the current step's file map from `docs/superpowers/plans/`
- Flags files created that are not in the current step's plan
- Flags dependencies added that are not needed until a later step
- Checks that work aligns with the current step's proof criteria

**Pass condition:** All changes align with the current build step's scope and file map.

**References:** SPEC_v6 §13 (build sequence and proof criteria), step plans in `docs/superpowers/plans/`.

---

## Agent: `wizard-review`

### Purpose

Orchestrates the individual skills intelligently based on what changed. Provides a single consolidated report.

### Trigger Points

- **On demand:** User invokes directly
- **Automatic:** Hooked into `superpowers:verification-before-completion` and `superpowers:requesting-code-review` flows

### Behavior

1. **Diff analysis** — Reads `git diff` (staged + unstaged) to determine changed files and which layers are touched.

2. **Skill selection** — Maps changed files to relevant skills:

| Files touched | Skills triggered |
|---|---|
| `integrations/`, `security/`, `data/` | pii, boundaries |
| `services/`, `orchestrator/`, `core/` | boundaries, scope, step |
| `llm/` | boundaries, types, scope |
| `shared/` | boundaries, types |
| `tests/` | tests |
| `prisma/` | types |
| Any file | scope (always runs) |

3. **Parallel execution** — Runs selected skills concurrently as subagents.

4. **Consolidation** — Collects results into a single report:

```
## Wizard Review

### FAIL — Layer Boundary (2 issues)
- services/task-service.ts:14 — imports PrismaClient directly instead of TaskRepository
- orchestrator/session.ts:38 — parses meeting keyPoints (interprets semantic content)

### FAIL — Placeholder Tests (1 issue)
- tests/contracts/data-to-mcp.test.ts:22 — empty test body, no assertions

### PASS — PII
### PASS — Types
### PASS — Scope
### SKIP — Step (no plan files changed)

Result: 2 FAIL / 3 PASS / 1 SKIP
```

5. **Exit behavior** — Returns the report. Does not auto-fix. The developer decides what to act on.

### What the Agent Does NOT Do

- Does not run tests (`yarn test`)
- Does not type-check (`yarn tsc --noEmit`)
- Does not modify code
- Does not block commits — it reports, you decide
