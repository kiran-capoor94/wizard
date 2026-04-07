# Wizard Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create six Claude Code quality-gate skills and one orchestrating agent that catch Wizard architecture violations before they land.

**Architecture:** Each skill is a standalone `SKILL.md` file in `~/.claude/skills/<name>/`. The agent is a standalone `.md` in `~/.claude/agents/`. Skills contain natural-language check instructions with concrete patterns to grep for. The agent reads `git diff`, selects relevant skills, dispatches subagents in parallel, and consolidates a pass/fail report.

**Tech Stack:** Claude Code skills (markdown), Claude Code agents (markdown). No runtime code — these are prompt-based quality gates executed by Claude Code itself.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `~/.claude/skills/wizard-check-pii/SKILL.md` | PII bypass and PII-in-tests detection |
| Create | `~/.claude/skills/wizard-check-boundaries/SKILL.md` | Layer boundary violation detection |
| Create | `~/.claude/skills/wizard-check-types/SKILL.md` | Type contract drift detection |
| Create | `~/.claude/skills/wizard-check-scope/SKILL.md` | Out-of-scope and removed component detection |
| Create | `~/.claude/skills/wizard-check-tests/SKILL.md` | Empty/placeholder test detection |
| Create | `~/.claude/skills/wizard-check-step/SKILL.md` | Build sequence violation detection |
| Create | `~/.claude/agents/wizard-review.md` | Orchestrating agent — runs relevant skills, consolidates report |

---

## Task 1: `/wizard-check-pii` Skill

**Files:**
- Create: `~/.claude/skills/wizard-check-pii/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/wizard-check-pii
```

- [ ] **Step 2: Write the skill file**

Create `~/.claude/skills/wizard-check-pii/SKILL.md` with the following content:

```markdown
---
name: wizard-check-pii
description: >
  Use when you want to check for PII leaks in the Wizard codebase. Detects raw integration data
  bypassing the Security layer and PII patterns in test fixtures. Invoke with /wizard-check-pii.
---

# PII Leak Detection

Check the Wizard codebase for PII bypass and PII in test data. Report findings in the format below.

## What To Check

### 1. Integration-to-Data Bypass

Search for import statements in files under `data/`, `services/`, `orchestrator/`, and `llm/` that import from `integrations/`.

The legal dependency flow is: `Integration → Security → Data`. Any direct import from `integrations/` into `data/`, `services/`, `orchestrator/`, or `llm/` bypasses the Security layer.

**How to check:**
- Use Grep to search for `from.*integrations/` or `require.*integrations/` in all `.ts` files under `data/`, `services/`, `orchestrator/`, and `llm/`.
- Each match is a FAIL.

### 2. PII Patterns in Test Fixtures

Search all files under `tests/` and any seed/fixture files for real-looking PII:

- **Email addresses:** Patterns like `user@example.com` are fine. Patterns like `john.smith@nhs.net`, `kiran@sisu.com`, or any email that looks like a real person are a FAIL.
- **UK phone numbers:** Patterns matching `+44`, `07\d{9}`, `01\d{9,10}`.
- **NHS numbers:** 10-digit numbers matching `\d{3}\s?\d{3}\s?\d{4}`.
- **Real names in clinical context:** Strings like "Patient John Smith" or "Dr. Jane Doe" in test data.

**How to check:**
- Use Grep with the patterns above across `tests/` and any files containing `seed`, `fixture`, or `mock` in their path.
- Real-person-looking emails and phone numbers are a FAIL. Generic placeholders (`test@test.com`, `+440000000000`) are fine.

### 3. PII Stubbing Instead of Scrubbing

Search for code that replaces PII with placeholder values (stubbing) instead of removing it entirely (scrubbing).

**How to check:**
- Use Grep for patterns like `replace.*PII`, `redact`, `mask`, `placeholder`, `[REDACTED]`, `***`, `XXX` in `security/` and `services/`.
- PII must be removed, not replaced. Any stubbing/masking logic is a FAIL.

## Output Format

Report as:

```
## PII Check

### PASS — No integration bypass detected
### FAIL — PII in test fixtures (N issues)
- tests/contracts/seed.ts:15 — real-looking email "john.smith@nhs.net"
- tests/unit/fixtures.ts:42 — NHS number pattern "123 456 7890"

### PASS — No PII stubbing detected

Result: PASS / FAIL
```

If all checks pass, report `Result: PASS`. If any check fails, report `Result: FAIL`.
```

- [ ] **Step 3: Verify the skill is discoverable**

```bash
ls ~/.claude/skills/wizard-check-pii/SKILL.md
```

Expected: file exists.

- [ ] **Step 4: Commit**

```bash
cd ~/.claude && git init 2>/dev/null; cd -
```

No git commit needed — `~/.claude` is not a tracked repo. Skill is live immediately.

---

## Task 2: `/wizard-check-boundaries` Skill

**Files:**
- Create: `~/.claude/skills/wizard-check-boundaries/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/wizard-check-boundaries
```

- [ ] **Step 2: Write the skill file**

Create `~/.claude/skills/wizard-check-boundaries/SKILL.md` with the following content:

```markdown
---
name: wizard-check-boundaries
description: >
  Use when you want to check for layer boundary violations in the Wizard codebase. Detects services
  calling Postgres directly, orchestrator interpreting semantic content, LLM layer reaching external
  systems, and wrong dependency directions. Invoke with /wizard-check-boundaries.
---

# Layer Boundary Violation Detection

Check the Wizard codebase for layer responsibility violations. The canonical dependency flow is:

```
Integration → Security → Data ← Orchestration → LLM Layer → Data
```

Report findings in the format below.

## What To Check

### 1. Services Bypassing Repositories

Services must call repositories in `data/`, never Prisma directly.

**How to check:**
- Use Grep to search for `PrismaClient`, `@prisma/client`, or `prisma.` in all `.ts` files under `services/`.
- Each match is a FAIL. Services must import from `data/` repositories only.

### 2. Orchestrator Interpreting Semantic Content

The orchestrator controls flow only. It must never parse, evaluate, or interpret the content of meetings, notes, tasks, or LLM output.

**How to check:**
- Read all `.ts` files under `orchestrator/`.
- Look for code that accesses `.keyPoints`, `.content`, `.outline`, `.description` and does anything with the values beyond passing them through (e.g., string operations, conditionals based on content, regex matching on content fields).
- Flow control (checking `.status`, `.id`, `.type`) is fine. Content interpretation is a FAIL.

### 3. LLM Layer Reaching External Systems

The LLM layer (`llm/`) must never import from `integrations/` or make HTTP/fetch calls to external systems.

**How to check:**
- Use Grep to search for `from.*integrations/`, `require.*integrations/`, `fetch(`, `axios`, `http.`, `https.` in all `.ts` files under `llm/`.
- Imports from `llm/` internal modules and `shared/` are fine. Everything else is suspect — check manually.

### 4. Business Logic in shared/

`shared/` must contain only types, interfaces, constants, and re-exports. No functions with logic, no classes with methods that do work.

**How to check:**
- Read all `.ts` files under `shared/`.
- Flag any function that does more than re-export or type-guard. Utility functions that compute, transform, or make decisions are a FAIL.

### 5. Workflow Definitions in orchestrator/

Workflow definitions belong in `core/`. `orchestrator/` executes them.

**How to check:**
- Use Grep to search for `workflow`, `WorkflowDefinition`, `steps:`, `pipeline` definitions in `orchestrator/`.
- Workflow execution logic (running steps, checking status) is fine. Workflow definition (declaring what steps exist, their order, their config) is a FAIL.

### 6. Context Assembly in orchestrator/

Context assembly belongs in `services/`. `orchestrator/` calls services, never assembles context itself.

**How to check:**
- Look in `orchestrator/` for code that queries repositories directly or builds `TaskContext` / context objects by assembling data from multiple sources.
- Calling a service method that returns assembled context is fine. Building context inline is a FAIL.

### 7. Wrong Dependency Direction in core/

`core/` must never import from `orchestrator/` or `services/`. It declares; they consume.

**How to check:**
- Use Grep to search for `from.*orchestrator/` or `from.*services/` in all `.ts` files under `core/`.
- Each match is a FAIL.

## Output Format

```
## Layer Boundary Check

### FAIL — Services Bypassing Repositories (1 issue)
- services/task-service.ts:14 — imports PrismaClient directly

### PASS — Orchestrator semantic content
### PASS — LLM layer isolation
### PASS — shared/ purity
### PASS — Workflow definitions in core/
### PASS — Context assembly in services/
### PASS — core/ dependency direction

Result: PASS / FAIL
```
```

- [ ] **Step 3: Verify the skill is discoverable**

```bash
ls ~/.claude/skills/wizard-check-boundaries/SKILL.md
```

- [ ] **Step 4: Smoke test**

Start a new Claude Code session in the Wizard project directory and invoke `/wizard-check-boundaries`. Verify it runs the checks and produces output in the expected format.

---

## Task 3: `/wizard-check-types` Skill

**Files:**
- Create: `~/.claude/skills/wizard-check-types/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/wizard-check-types
```

- [ ] **Step 2: Write the skill file**

Create `~/.claude/skills/wizard-check-types/SKILL.md` with the following content:

```markdown
---
name: wizard-check-types
description: >
  Use when you want to check for type contract drift in the Wizard codebase. Detects re-declared
  Prisma enums, wrong nullability, string IDs, and embedding dimension mismatches.
  Invoke with /wizard-check-types.
---

# Type Contract Drift Detection

Check the Wizard codebase for type contract drift from the Prisma source of truth. Report findings in the format below.

## What To Check

### 1. Re-declared Prisma Enums

These enums must only exist in `prisma/schema.prisma` and be re-exported from `shared/types.ts`. They must never be re-declared as TypeScript enums or union types anywhere else:

`TaskStatus`, `TaskType`, `TaskPriority`, `SessionStatus`, `WorkflowStatus`, `NoteType`, `NoteParent`, `RepoProvider`

**How to check:**
- Use Grep to search for `enum TaskStatus`, `enum TaskType`, `enum TaskPriority`, `enum SessionStatus`, `enum WorkflowStatus`, `enum NoteType`, `enum NoteParent`, `enum RepoProvider` in all `.ts` files.
- Also search for these as union types: `type TaskStatus =`, `type TaskType =`, etc.
- Matches in `shared/types.ts` that are re-exports (`export { TaskStatus } from`) are fine.
- Matches in `generated/prisma/` are fine (Prisma-generated).
- Any other match is a FAIL — the enum is being re-declared.

### 2. Wrong Nullability

Prisma uses `null` for optional fields, not `undefined`. All optional fields in Wizard types must use `| null`.

**How to check:**
- Use Grep to search for `?: ` (optional property syntax) in type/interface definitions under `shared/`, `data/`, `services/`, `orchestrator/`, `llm/`, `core/`.
- For each match, check if the field corresponds to a nullable Prisma field. If it does, it should be `fieldName: Type | null` not `fieldName?: Type`.
- `undefined` is acceptable for function parameters that are truly optional. It is NOT acceptable for data types that mirror Prisma models.

### 3. String IDs

All entity IDs in Wizard are autoincrement integers, not strings.

**How to check:**
- Use Grep to search for `id: string`, `taskId: string`, `sessionId: string`, `meetingId: string`, `noteId: string`, `repoId: string`, `userId: string` in all `.ts` files under `shared/`, `data/`, `services/`, `orchestrator/`, `llm/`, `core/`.
- Each match is a FAIL. IDs must be `number`.

### 4. TaskContext Location

`TaskContext` must be defined in `shared/types.ts` only.

**How to check:**
- Use Grep to search for `interface TaskContext` or `type TaskContext` in all `.ts` files.
- A match in `shared/types.ts` is expected. Any other match is a FAIL.

### 5. Embedding Dimensions

All embeddings must be `vector(768)` — nomic-embed-text dimensions. Not 1536, not 384, not any other value.

**How to check:**
- Use Grep to search for `vector(` in all files under `prisma/`, `data/`, and any migration files.
- Every match must be `vector(768)`. Any other dimension is a FAIL.
- Also search for dimension constants: `1536`, `384`, `256` near embedding-related code in `llm/` and `data/`. Flag if they appear as vector dimensions.

## Output Format

```
## Type Contract Check

### PASS — Prisma enums not re-declared
### FAIL — Wrong nullability (2 issues)
- shared/types.ts:45 — taskId?: number should be taskId: number | null
- services/context.ts:12 — meetingId?: number should be meetingId: number | null

### PASS — IDs are integers
### PASS — TaskContext in shared/types.ts
### PASS — Embedding dimensions are vector(768)

Result: PASS / FAIL
```
```

- [ ] **Step 3: Verify the skill is discoverable**

```bash
ls ~/.claude/skills/wizard-check-types/SKILL.md
```

---

## Task 4: `/wizard-check-scope` Skill

**Files:**
- Create: `~/.claude/skills/wizard-check-scope/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/wizard-check-scope
```

- [ ] **Step 2: Write the skill file**

Create `~/.claude/skills/wizard-check-scope/SKILL.md` with the following content:

```markdown
---
name: wizard-check-scope
description: >
  Use when you want to check for out-of-scope or removed components in the Wizard codebase.
  Detects implementations that were explicitly removed from v2 or listed as out of scope in
  SPEC_v6. Invoke with /wizard-check-scope.
---

# Out-of-Scope & Removed Component Detection

Check the Wizard codebase for components that were explicitly removed from v2 (SPEC_v6 §11) or declared out of scope (SPEC_v6 §16). Report findings in the format below.

## What To Check

### 1. Removed Components (SPEC_v6 §11)

These were designed then explicitly removed. They must not appear in the codebase:

**Queues and DLQ:**
- Search for `queue`, `Queue`, `DLQ`, `dead.letter`, `bull`, `bullmq`, `amqp`, `rabbitmq`, `kafka`, `SQS`, `background.job`, `worker.thread` in all `.ts` files (excluding `node_modules/` and `docs/`).
- Any implementation of queue or background job infrastructure is a FAIL. References in comments explaining why they were removed are fine.

**Exaggeration detection:**
- Search for `exaggerat` in all `.ts` files.
- Any implementation is a FAIL.

**Hallucination detection:**
- Search for `hallucin` in all `.ts` files.
- Any implementation is a FAIL. Note: attribution check via pgvector similarity is allowed and distinct — it lives in the output pipeline as a data integrity check, not a hallucination detector.

**Full eval framework:**
- Check the `evals/` directory. It should contain scaffold only — dataset format definition and a runner stub.
- If `evals/` contains working evaluation pipelines, scoring logic, or model comparison infrastructure, that is a FAIL. Scaffold = type definitions + empty runner.

**Four code intelligence structures:**
- Search for `LSPSymbol`, `TreeSitter`, `tree.sitter`, `call.map`, `CallMap`, `call.graph`, `CallGraph`, `inheritance.map`, `InheritanceMap`, `AST` (as a type/class, not in comments) in all `.ts` files.
- Any implementation is a FAIL. `CodeChunkEmbedding` and Serena live traversal are the correct replacements.

### 2. Out of Scope (SPEC_v6 §16)

These are explicitly out of scope for v2:

**Hosting / cloud / multi-tenancy:**
- Search for `deploy`, `Dockerfile` (beyond docker-compose for local Postgres), `kubernetes`, `k8s`, `terraform`, `AWS`, `GCP`, `Azure`, `tenant`, `multi.tenant` in `.ts` files and config files.
- Local Docker for Postgres is fine. Cloud deployment infrastructure is a FAIL.

**PII stubbing/replacement:**
- Search for `[REDACTED]`, `[REMOVED]`, `***`, `placeholder`, `stub` in `security/` code that deals with PII.
- PII must be scrubbed (removed entirely), not stubbed/replaced. Any replacement logic is a FAIL.

**Dynamic workflow definitions:**
- Search for code that loads workflow definitions from a database, config file, or external source in `core/` or `orchestrator/`.
- Workflows must be hardcoded in `core/`. Dynamic loading is a FAIL.

**Authentication/auth middleware:**
- Search for `auth`, `jwt`, `token.verify`, `session.token`, `passport`, `bcrypt`, `password` in all `.ts` files (excluding `integrations/` where API tokens for external services are expected).
- The `User` model exists but auth is deferred. Any auth middleware or login flow is a FAIL.

**Clinical data handling:**
- Search for `clinical`, `patient`, `diagnosis`, `prescription`, `medical.record`, `NHS.record` in all `.ts` files.
- Any pipeline that processes clinical data is a FAIL. Engineering context only in v2.

**LSP integration directly in Wizard:**
- Search for `lsp`, `language.server`, `LSPClient` in all `.ts` files (excluding references to Serena).
- Serena provides the LSP bridge. Direct LSP integration in Wizard is a FAIL.

## Output Format

```
## Scope Check

### PASS — No removed components
### FAIL — Out of scope (1 issue)
- security/scrubber.ts:28 — PII stubbing with [REDACTED] instead of scrubbing

Result: PASS / FAIL
```
```

- [ ] **Step 3: Verify the skill is discoverable**

```bash
ls ~/.claude/skills/wizard-check-scope/SKILL.md
```

---

## Task 5: `/wizard-check-tests` Skill

**Files:**
- Create: `~/.claude/skills/wizard-check-tests/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/wizard-check-tests
```

- [ ] **Step 2: Write the skill file**

Create `~/.claude/skills/wizard-check-tests/SKILL.md` with the following content:

```markdown
---
name: wizard-check-tests
description: >
  Use when you want to check for empty, placeholder, or weak tests in the Wizard codebase.
  Detects it.todo(), empty test bodies, weak-only assertions, and mock-heavy tests that don't
  verify behavior. Invoke with /wizard-check-tests.
---

# Empty & Placeholder Test Detection

Check the Wizard test suite for tests that look like progress but assert nothing. Report findings in the format below.

## What To Check

### 1. Todo Tests

**How to check:**
- Use Grep to search for `it\.todo\(`, `test\.todo\(`, `xit\(`, `xtest\(`, `it\.skip\(`, `test\.skip\(` in all `.ts` files under `tests/`.
- Each match is a FAIL. Tests must be implemented or removed, not left as todos.

### 2. Empty Test Bodies

**How to check:**
- Use Grep with multiline mode to search for test bodies that are empty or contain only trivially true assertions.
- Patterns to catch:
  - `test\(.*,\s*\(\)\s*=>\s*\{\s*\}\)` — empty arrow function body
  - `test\(.*,\s*function\s*\(\)\s*\{\s*\}\)` — empty function body
  - `expect(true).toBe(true)` or `expect(1).toBe(1)` as the only assertion
- Each match is a FAIL.

### 3. Weak-Only Assertions

A test that only asserts existence without checking actual values is a placeholder in disguise.

**How to check:**
- For each test block (`it(` or `test(`), check if the ONLY expect statements are:
  - `expect(...).toBeDefined()`
  - `expect(...).toBeTruthy()`
  - `expect(...).not.toBeNull()`
  - `expect(...).not.toBeUndefined()`
- If a test has ONLY these weak assertions and no specific value/property assertions, it is a FAIL.
- If a test has weak assertions PLUS specific assertions (e.g., `expect(result.id).toBe(1)`), that is fine — the weak assertion is just a guard.

### 4. Empty Describe Blocks

**How to check:**
- Use Grep with multiline mode to find `describe(` blocks that contain no `it(` or `test(` children.
- Each match is a FAIL.

### 5. Mock-Heavy Tests

Tests that mock the thing they're supposed to test.

**How to check:**
- For each test file, check if the primary module under test is mocked. For example:
  - A test for `TaskRepository` that mocks `TaskRepository` — FAIL.
  - A test for `TaskService` that mocks the repository it calls — fine (testing service logic, not repository).
- Also flag tests where more than half the test body is mock setup and the actual assertion is trivial.
- This check requires reading the test files and understanding what they test. Use judgement.

## Output Format

```
## Test Quality Check

### FAIL — Todo tests (2 issues)
- tests/contracts/data-to-mcp.test.ts:15 — it.todo("should return null for missing task")
- tests/unit/skill-injection.test.ts:8 — test.skip("template rendering")

### PASS — No empty test bodies
### FAIL — Weak-only assertions (1 issue)
- tests/contracts/data-to-mcp.test.ts:22 — only asserts toBeDefined(), no value checks

### PASS — No empty describe blocks
### PASS — No mock-heavy tests

Result: PASS / FAIL
```
```

- [ ] **Step 3: Verify the skill is discoverable**

```bash
ls ~/.claude/skills/wizard-check-tests/SKILL.md
```

---

## Task 6: `/wizard-check-step` Skill

**Files:**
- Create: `~/.claude/skills/wizard-check-step/SKILL.md`

- [ ] **Step 1: Create the skill directory**

```bash
mkdir -p ~/.claude/skills/wizard-check-step
```

- [ ] **Step 2: Write the skill file**

Create `~/.claude/skills/wizard-check-step/SKILL.md` with the following content:

```markdown
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
```

- [ ] **Step 3: Verify the skill is discoverable**

```bash
ls ~/.claude/skills/wizard-check-step/SKILL.md
```

---

## Task 7: `wizard-review` Agent

**Files:**
- Create: `~/.claude/agents/wizard-review.md`

- [ ] **Step 1: Create the agents directory**

```bash
mkdir -p ~/.claude/agents
```

- [ ] **Step 2: Write the agent file**

Create `~/.claude/agents/wizard-review.md` with the following content:

```markdown
---
name: wizard-review
description: |
  Use this agent to run Wizard architecture quality gates against changed code. It reads git diff,
  selects which checks are relevant based on which files changed, runs them in parallel, and
  returns a consolidated pass/fail report. Use after completing a chunk of work, before committing,
  or as part of code review. Examples: <example>Context: User has finished implementing a repository layer. user: "I've finished the task repository" assistant: "Let me run the wizard-review agent to check the implementation against Wizard's architecture invariants" <commentary>Code was written in data/ and services/ — the agent will run boundaries, types, scope, step, and test checks.</commentary></example> <example>Context: User wants a quality check before committing. user: "run wizard review" assistant: "Running the wizard-review agent to check for architecture violations" <commentary>User explicitly requested a review — run all relevant checks based on git diff.</commentary></example>
model: inherit
tools: Glob, Grep, LS, Read, Bash, Agent
---

You are the Wizard architecture review agent. Your job is to check code changes against Wizard's architecture invariants and produce a consolidated report.

## Process

### Step 1: Analyze the Diff

Run `git diff --name-only` and `git diff --cached --name-only` to get all changed files (staged and unstaged).

If there are no changed files, report "No changes to review" and exit.

### Step 2: Select Checks

Map changed files to relevant checks using this table:

| Files touched | Checks to run |
|---|---|
| `integrations/`, `security/`, `data/` | pii, boundaries |
| `services/`, `orchestrator/`, `core/` | boundaries, scope, step |
| `llm/` | boundaries, types, scope |
| `shared/` | boundaries, types |
| `tests/` | tests |
| `prisma/` | types |

**Always run:** scope (cheapest check, highest value — catches removed/out-of-scope components regardless of where they appear).

Deduplicate — if boundaries is triggered by two different directories, run it once.

### Step 3: Execute Checks

For each selected check, perform the analysis described below. Run checks in parallel where possible by reading all relevant files upfront.

**PII Check:**
1. Grep for `from.*integrations/` in `.ts` files under `data/`, `services/`, `orchestrator/`, `llm/`. Each match = FAIL.
2. Grep for real-looking PII patterns in `tests/`: real emails (not `test@test.com`), UK phone numbers (`+44`, `07\d{9}`), NHS numbers (`\d{3}\s?\d{3}\s?\d{4}`), real names in clinical strings.
3. Grep for PII stubbing patterns (`[REDACTED]`, `[REMOVED]`, `mask`, `placeholder`) in `security/`.

**Boundaries Check:**
1. Grep for `PrismaClient`, `@prisma/client` in `services/`. Each match = FAIL.
2. Read `orchestrator/` files — flag semantic content interpretation (accessing `.keyPoints`, `.content`, `.outline` and doing logic on values).
3. Grep for `from.*integrations/`, `fetch(`, `axios` in `llm/`. Each match = FAIL.
4. Read `shared/` files — flag any business logic (functions that compute, transform, decide).
5. Grep for workflow definitions in `orchestrator/` — declaring step sequences, pipeline configs.
6. Look for context assembly (building `TaskContext`, querying multiple repos) in `orchestrator/`.
7. Grep for `from.*orchestrator/` or `from.*services/` in `core/`. Each match = FAIL.

**Types Check:**
1. Grep for enum re-declarations: `enum TaskStatus`, `type TaskStatus =`, etc. in `.ts` files outside `shared/types.ts` and `generated/`.
2. Grep for `?: ` in type definitions under `shared/`, `data/`, `services/` — check if Prisma nullable fields use `| null`.
3. Grep for `id: string`, `taskId: string`, etc. IDs must be `number`.
4. Grep for `interface TaskContext` or `type TaskContext` outside `shared/types.ts`.
5. Grep for `vector(` — must always be `vector(768)`.

**Scope Check:**
1. Grep for removed components: `queue`, `DLQ`, `exaggerat`, `hallucin`, `TreeSitter`, `CallMap`, `CallGraph`, `InheritanceMap`.
2. Grep for out-of-scope items: `[REDACTED]` in security code, dynamic workflow loading, auth middleware (`jwt`, `passport`, `bcrypt`), clinical data terms, direct LSP code.

**Tests Check:**
1. Grep for `it\.todo\(`, `test\.todo\(`, `xit\(`, `xtest\(`, `it\.skip\(`, `test\.skip\(` in `tests/`.
2. Look for empty test bodies and trivially true assertions.
3. Identify tests where the only assertions are `toBeDefined()`, `toBeTruthy()`, `not.toBeNull()`.
4. Read test files to check for mock-heavy tests that mock the subject under test.

**Step Check:**
1. Read `AGENTS.md` for current step number.
2. Read the current step's plan from `docs/superpowers/plans/`.
3. Check if any changed files belong to a future step.
4. Check `package.json` for premature dependencies.

### Step 4: Consolidate Report

Produce a single report in this exact format:

```
## Wizard Review

### FAIL — [Check Name] (N issues)
- file/path.ts:line — description of violation

### PASS — [Check Name]

### SKIP — [Check Name] (reason)

Result: N FAIL / N PASS / N SKIP
```

Order: FAIL sections first, then PASS, then SKIP. Include the total count at the bottom.

### Step 5: Exit

Return the report. Do NOT auto-fix issues. Do NOT modify any files. The developer decides what to act on.
```

- [ ] **Step 3: Verify the agent is discoverable**

```bash
ls ~/.claude/agents/wizard-review.md
```

---

## Task 8: End-to-End Smoke Test

- [ ] **Step 1: Test individual skill — `/wizard-check-tests`**

Open a new Claude Code session in the Wizard project directory. Run:

```
/wizard-check-tests
```

Verify it scans `tests/` and produces output in the expected format with PASS/FAIL sections.

- [ ] **Step 2: Test individual skill — `/wizard-check-boundaries`**

In the same or new session, run:

```
/wizard-check-boundaries
```

Verify it checks import paths and produces the boundary check report.

- [ ] **Step 3: Test the agent**

Run:

```
Run the wizard-review agent against my current changes.
```

Verify it:
1. Reads git diff
2. Selects relevant checks
3. Runs them
4. Produces a consolidated report with the correct format

- [ ] **Step 4: Fix any issues found during smoke testing**

If any skill or the agent doesn't behave as expected, edit the relevant `.md` file and re-test. Common issues:
- Grep patterns too broad (false positives) — tighten the pattern
- Grep patterns too narrow (missing violations) — broaden the pattern
- Agent not finding the skill files — check directory naming matches `name` in frontmatter
