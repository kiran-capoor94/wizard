# Spec v8 Alignment — Design Document

| Field | Value |
|---|---|
| Date | 2026-04-07 |
| Author | Kiran Capoor |
| Status | Approved |

---

## Context

SPEC_v8.md is the updated canonical architecture specification for Wizard v2. Several existing documents — AGENTS.md, the Step 1 design spec, and all 5 implementation plans — contain references that conflict with SPEC_v8. This document captures every delta and the surgical edit required to bring all docs into alignment.

---

## 1. AGENTS.md

### Project Structure

Replace the directory tree. Remove `orchestrator/` as a top-level directory. Nest `cli/`, `mcp/`, `plugin/` under `interfaces/`.

```
wizard/
├── llm/            # Model-agnostic LLM layer
│   ├── adapters/   # LLM adapters + EmbeddingAdapter (independent interfaces)
│   ├── prompts/    # Model-agnostic skill templates
│   ├── schemas/    # I/O contracts, validators
│   └── packaging/  # Renders + deploys templates to model-specific locations
├── interfaces/
│   ├── cli/        # Human interface — all wizard commands
│   ├── mcp/        # MCP server — wizard tools callable by LLM agents
│   └── plugin/     # IDE plugin interface (Neovim, VS Code, Claude Desktop)
├── shared/         # Shared types, constants, base structs and interfaces
├── core/           # Workflow definitions, domain rules, base error classes
├── services/       # Context assembly, workflow execution, pre-flight, session lifecycle
├── data/           # Postgres + pgvector — migrations, schema, repositories
├── security/       # PII detection — HTTP client to Presidio sidecar
├── integrations/   # Notion, Jira, Krisp, GitHub
├── evals/          # Eval scaffolding — dataset format, runner stub
└── tests/
    ├── contracts/  # Contract tests at every layer boundary
    └── unit/       # Unit tests — variable injection, pipeline ordering, PII
```

### Key Distinctions

Update to remove orchestrator references:

- `llm/prompts/` defines skills. `services/` injects variables at runtime.
- `core/` declares workflows. `services/` executes them.
- `data/` owns repositories. Services call repositories, never Postgres directly.
- `llm/adapters/` has two independent interfaces: `LLMAdapter` (generate) and `EmbeddingAdapter` (embed).
- `services/` owns context assembly, workflow execution, session lifecycle, and pre-flight.
- `shared/` is types and constants only. Never business logic.
- `evals/` is a dev tool, not part of the system.

### Dependency Flow

```
Integration → Security → Data ← Services → Output Pipeline → Data
```

### Code Style — TypeScript

- Target: **ES2023** (was ES2022)
- Module resolution: **bundler** (was Node16)
- ESM with `.js` extensions in imports (unchanged)

### Build Sequence Table

| Step | Build | Proof |
|------|-------|-------|
| 1 | Postgres schema, pgvector, repositories, services, first skill | Contract test: LLM layer receives exactly what Postgres contains |
| 2 | Services layer with session lifecycle, workflow execution, pre-flight | LLM invoked by service function with prepared context |
| 3 | First integration (Notion), PII scrubbing via Presidio, config | Raw data enters, PII removed, clean data reaches LLM |
| 4 | LLM output pipeline: process → transform → validate → store → materialise | Invalid output rejected, correct output retrievable |
| 5 | All integrations, task-type context, CodeChunkEmbedding, CLI, evals | Full session flow end-to-end |

---

## 2. Step 1 Design Spec (`2026-04-03-wizard-v2-step1-design.md`)

### Directory Structure

- `mcp/` → `interfaces/mcp/`
- Add `interfaces/cli/` and `interfaces/plugin/` as placeholder directories
- tsconfig `include`: replace `"mcp/**/*.ts"` with `"interfaces/**/*.ts"`

### MCP Interface

- Call chain path: `mcp/index.ts` → `interfaces/mcp/index.ts`

### Skill Template

- "Orchestration (Step 2) does a direct string substitution" → "Services layer (Step 2) does a direct string substitution"

### CodeChunkEmbedding Schema

- Replace `startLine Int` / `endLine Int` with `chunkIndex Int`
- Unique constraint: `@@unique([repoId, filePath, startLine, endLine])` → `@@unique([repoId, filePath, chunkIndex])`

### Blast Radius

- `mcp/index.ts compiles to build/mcp/index.js` → `interfaces/mcp/index.ts compiles to build/interfaces/mcp/index.js`
- "post-Step 2 would require Orchestration refactoring" → "post-Step 2 would require services refactoring"

---

## 3. Step 1 Plan (`2026-04-03-wizard-v2-step1.md`)

### Tech Stack

- `TypeScript (ESM, Node16)` → `TypeScript (ESM, bundler)`

### File Map

- `mcp/index.ts` → `interfaces/mcp/index.ts`

### Task 1 (Bootstrap)

- `package.json` bin: `"./build/mcp/index.js"` → `"./build/interfaces/mcp/index.js"`
- Build script chmod path updated accordingly

### Task 2 (Restructure)

- `mkdir` command: replace `mcp` with `interfaces/mcp interfaces/cli interfaces/plugin`
- tsconfig include: `"mcp/**/*.ts"` → `"interfaces/**/*.ts"`
- `mcp/index.ts` → `interfaces/mcp/index.ts`

### Task 3 (Prisma Schema)

- CodeChunkEmbedding: `startLine`/`endLine` → `chunkIndex Int`
- Unique constraint updated to `@@unique([repoId, filePath, chunkIndex])`

### All tsconfig Snippets

- `"target": "ES2022"` → `"target": "ES2023"`
- `"moduleResolution": "Node16"` → `"moduleResolution": "bundler"`

---

## 4. Step 2 Plan (`2026-04-04-wizard-v2-step2.md`) — Major Rewrite

### Title

"Orchestration → Data → LLM Layer" → "Services Layer — Session Lifecycle & Workflow Execution"

### Remove Task 0 (Serena Spike)

SPEC_v8 explicitly closed this: "Wizard does not invoke Serena. No spike needed." Delete the entire Serena spike task and its documentation steps.

### All File Paths

- `orchestrator/inject.ts` → `services/inject.ts`
- `orchestrator/preflight.ts` → `services/preflight.ts`
- `orchestrator/session.ts` → `services/session.ts`
- `orchestrator/workflow.ts` → `services/workflow.ts`
- All test imports updated accordingly
- `tests/contracts/orchestration-to-llm.test.ts` → `tests/contracts/services-to-llm.test.ts`

### Architecture Paragraph

Rewrite to: "Each workflow is a service function. No separate orchestration layer. Pre-flight is a shared utility called at the start of every service function — not an interface concern. WorkflowRun audit trail is written inside service functions, before and after execution."

### tsconfig Snippets

- Remove `"orchestrator/**/*.ts"` from include (already has `"services/**/*.ts"`)
- ES2022 → ES2023, moduleResolution → bundler

### MCP Paths

- `mcp/index.ts` → `interfaces/mcp/index.ts`

### Task Renumbering

Tasks 1–7 shift to account for Task 0 removal. Commit messages updated to reference `services/` not `orchestrator/`.

---

## 5. Step 3 Plan (`2026-04-04-wizard-v2-step3.md`)

### PII Scrubbing — Presidio Sidecar

Replace the custom regex-based PII scrubber with a Presidio Docker sidecar:

- `security/scrub.ts` — Rewrite from regex detection to HTTP client calling Presidio REST API (~50 lines). Remove all custom regex patterns. Presidio provides 50+ built-in recognisers including NHS numbers.
- `security/types.ts` — Keep `ScrubResult`, `AuditEntry` types
- `docker-compose.yaml` — Add Presidio analyzer and anonymizer services alongside Postgres
- Unit test for regex PII detection → integration test against Presidio sidecar
- Contract tests verify Presidio integration, not regex accuracy

### Path Updates

- `cli/index.ts` → `interfaces/cli/index.ts`
- `cli/commands/setup.ts` → `interfaces/cli/commands/setup.ts`
- `mcp/` → `interfaces/mcp/`
- tsconfig includes: `"cli/**/*.ts"` → already covered by `"interfaces/**/*.ts"`

### Tech Stack

- ES2022/Node16 → ES2023/bundler

### wizard setup

Update description: starts Presidio sidecar alongside Postgres via docker-compose.

---

## 6. Step 4 Plan (`2026-04-04-wizard-v2-step4.md`)

### Tech Stack

- ES2022/Node16 → ES2023/bundler

### Materialise Step

Add to the pipeline after `store`: "For skills flagged `materialise: true` in `core/`, create a Note entity (investigation or decision type), link to current Task and Session, trigger embedding. One function, not a framework."

Pipeline becomes: process → transform → validate → store → materialise.

### Architecture References

- Remove any orchestrator references. Pipeline is called from service functions.
- `mcp/` → `interfaces/mcp/` in any paths

---

## 7. Step 5 Plan (`2026-04-04-wizard-v2-step5.md`)

### Remove

- `integrations/serena/invoke.ts` — Wizard never invokes Serena. Remove from file map and all tasks.
- `llm/adapters/openai.ts` — Second adapter deferred to v3. Remove from file map.
- `tests/contracts/llm-adapter-openai.test.ts` — Remove.
- Task 8 (second LLM adapter) — Delete entirely.

### Add

- CodeChunkEmbedding chunking: `@langchain/textsplitters` dependency, `RecursiveCharacterTextSplitter` with chunk size 512 tokens, overlap 256.
- `chunkIndex` field (not `startLine/endLine`) in all CodeChunkEmbedding references.

### Update

- Goal description: remove "second LLM adapter (model-agnostic proof)"
- `cli/` paths → `interfaces/cli/`
- Tech stack: ES2022/Node16 → ES2023/bundler
- Add `@langchain/textsplitters` to dependencies

---

## Verification

All documents are aligned with SPEC_v8 when:

1. No file references `orchestrator/` as a directory or layer
2. All paths use `interfaces/mcp/`, `interfaces/cli/`, `interfaces/plugin/`
3. All tsconfig snippets use ES2023 target and bundler moduleResolution
4. CodeChunkEmbedding uses `chunkIndex`, not `startLine/endLine`
5. No Serena spike or invocation references remain
6. No second LLM adapter (OpenAI) references remain
7. PII scrubbing references Presidio sidecar, not custom regex
8. Dependency flow shows `Services`, not `Orchestration`
