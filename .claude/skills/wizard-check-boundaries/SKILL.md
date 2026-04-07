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
