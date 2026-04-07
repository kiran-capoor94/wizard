# Spec v8 Document Alignment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surgically edit 7 documentation files (AGENTS.md, Step 1 design spec, Steps 1–5 plans) to align with SPEC_v8.md.

**Architecture:** No code changes. Each task edits one file using find-and-replace operations. Changes are grouped by file to minimise context switching. Each task ends with a commit.

**Tech Stack:** Markdown, git.

---

## File Map

| Action | Path | Summary |
|--------|------|---------|
| Modify | `AGENTS.md` | Remove orchestrator, add interfaces/, update ES target, fix dependency flow |
| Modify | `docs/superpowers/specs/2026-04-03-wizard-v2-step1-design.md` | mcp/ → interfaces/mcp/, CodeChunkEmbedding chunkIndex, remove orchestrator refs |
| Modify | `docs/superpowers/plans/2026-04-03-wizard-v2-step1.md` | mcp/ → interfaces/mcp/, ES2023/bundler, CodeChunkEmbedding chunkIndex |
| Modify | `docs/superpowers/plans/2026-04-04-wizard-v2-step2.md` | orchestrator/ → services/, remove Serena spike, ES2023/bundler |
| Modify | `docs/superpowers/plans/2026-04-04-wizard-v2-step3.md` | Custom PII → Presidio, cli/ → interfaces/cli/, ES2023/bundler |
| Modify | `docs/superpowers/plans/2026-04-04-wizard-v2-step4.md` | Add materialise step, ES2023/bundler, remove orchestrator refs |
| Modify | `docs/superpowers/plans/2026-04-04-wizard-v2-step5.md` | Remove Serena/OpenAI, add CodeChunkEmbedding details, cli/ → interfaces/cli/ |

---

## Task 1: AGENTS.md

**Files:**
- Modify: `AGENTS.md`

---

- [ ] **Step 1.1: Replace the project structure tree**

Replace this block:

```
wizard/
├── llm/            # Model-agnostic LLM layer
│   ├── adapters/   # LLM adapters + EmbeddingAdapter (independent interfaces)
│   ├── prompts/    # Model-agnostic skill templates
│   ├── schemas/    # I/O contracts, validators
│   └── packaging/  # Renders + deploys templates to model-specific locations
├── cli/            # Human interface — all wizard commands
├── shared/         # Shared types, constants, base structs and interfaces
├── core/           # Workflow definitions, domain rules, base error classes
├── services/       # Context assembly and operation execution
├── orchestrator/   # Workflow execution, session lifecycle, DB sync, pre-flight
├── data/           # Postgres + pgvector — migrations, schema, repositories
├── security/       # PII detection and scrubbing
├── integrations/   # Notion, Jira, Krisp, Serena, GitHub
├── plugin/         # Claude-specific skills (packaging target for Claude adapter)
├── evals/          # Eval scaffolding — dataset format, runner stub
└── tests/
    ├── contracts/  # Contract tests at every layer boundary
    └── unit/       # Unit tests — variable injection, pipeline ordering, PII
```

With:

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

- [ ] **Step 1.2: Replace the key distinctions block**

Replace:

```
Key distinctions:

- `llm/prompts/` defines skills. `orchestrator/` injects variables at runtime.
- `core/` declares workflows. `orchestrator/` executes them.
- `data/` owns repositories. Services call repositories, never Postgres directly.
- `llm/adapters/` has two independent interfaces: `LLMAdapter` (generate) and `EmbeddingAdapter` (embed).
- `services/` owns context assembly. `orchestrator/` owns workflow execution.
- `shared/` is types and constants only. Never business logic.
- `evals/` is a dev tool, not part of the system.
```

With:

```
Key distinctions:

- `llm/prompts/` defines skills. `services/` injects variables at runtime.
- `core/` declares workflows. `services/` executes them.
- `data/` owns repositories. Services call repositories, never Postgres directly.
- `llm/adapters/` has two independent interfaces: `LLMAdapter` (generate) and `EmbeddingAdapter` (embed).
- `services/` owns context assembly, workflow execution, session lifecycle, and pre-flight.
- `shared/` is types and constants only. Never business logic.
- `evals/` is a dev tool, not part of the system.
```

- [ ] **Step 1.3: Replace the dependency flow line**

Replace:

```
Dependency flow: `Integration → Security → Data ← Orchestration → LLM Layer → Data`
```

With:

```
Dependency flow: `Integration → Security → Data ← Services → Output Pipeline → Data`
```

- [ ] **Step 1.4: Update TypeScript config references**

Replace:

```
- **Strict mode** always. No `any` unless explicitly justified.
- **ESM** with `Node16` module resolution. Use `.js` extensions in imports.
- **Target**: ES2022.
```

With:

```
- **Strict mode** always. No `any` unless explicitly justified.
- **ESM** with `bundler` module resolution. Use `.js` extensions in imports.
- **Target**: ES2023.
```

- [ ] **Step 1.5: Update the build sequence table**

Replace:

```
| Step | Build | Proof |
|------|-------|-------|
| 1 | Postgres schema, pgvector, repositories, services, first skill | Contract test: LLM layer receives exactly what Postgres contains |
| 2 | Orchestration, session lifecycle, pre-flight | LLM invoked by Orchestration with prepared context |
| 3 | First integration (Notion), PII scrubbing, config | Raw data enters, PII removed, clean data reaches LLM |
| 4 | LLM output pipeline: process → transform → validate → store | Invalid output rejected, correct output retrievable |
| 5 | All integrations, task-type context, CLI, evals | Full session flow end-to-end |
```

With:

```
| Step | Build | Proof |
|------|-------|-------|
| 1 | Postgres schema, pgvector, repositories, services, first skill | Contract test: LLM layer receives exactly what Postgres contains |
| 2 | Services layer with session lifecycle, workflow execution, pre-flight | LLM invoked by service function with prepared context |
| 3 | First integration (Notion), PII scrubbing via Presidio, config | Raw data enters, PII removed, clean data reaches LLM |
| 4 | LLM output pipeline: process → transform → validate → store → materialise | Invalid output rejected, correct output retrievable |
| 5 | All integrations, task-type context, CodeChunkEmbedding, CLI, evals | Full session flow end-to-end |
```

- [ ] **Step 1.6: Update tech stack**

Replace:

```
- TypeScript (ESM, strict, Node16)
```

With:

```
- TypeScript (ESM, strict, bundler)
```

- [ ] **Step 1.7: Commit**

```bash
git add AGENTS.md
git commit -m "docs: align AGENTS.md with SPEC_v8 — remove orchestrator, add interfaces/"
```

---

## Task 2: Step 1 Design Spec

**Files:**
- Modify: `docs/superpowers/specs/2026-04-03-wizard-v2-step1-design.md`

---

- [ ] **Step 2.1: Replace directory structure tree**

Replace the `wizard/` tree in the Directory Structure section. Change `mcp/` to `interfaces/mcp/` and add `interfaces/cli/` and `interfaces/plugin/`:

Old:
```
├── mcp/
│   └── index.ts               # MCP server (migrated from src/index.ts)
```

New:
```
├── interfaces/
│   ├── mcp/
│   │   └── index.ts           # MCP server (migrated from src/index.ts)
│   ├── cli/                   # Placeholder — Step 3
│   └── plugin/                # Placeholder — Step 5
```

- [ ] **Step 2.2: Update tsconfig include list**

In the tsconfig.json changes section, replace:

```
- `include`: explicit list — `data/**/*.ts`, `mcp/**/*.ts`, `llm/**/*.ts`, `services/**/*.ts`, `shared/**/*.ts`, `integrations/**/*.ts`
```

With:

```
- `include`: explicit list — `data/**/*.ts`, `interfaces/**/*.ts`, `llm/**/*.ts`, `services/**/*.ts`, `shared/**/*.ts`, `integrations/**/*.ts`
```

- [ ] **Step 2.3: Update MCP Interface call chain**

Replace:

```
mcp/index.ts
  → data/repositories/task.ts :: getTaskContext(taskId)
```

With:

```
interfaces/mcp/index.ts
  → data/repositories/task.ts :: getTaskContext(taskId)
```

- [ ] **Step 2.4: Update skill template Orchestration reference**

Replace:

```
`llm/prompts/task_start.md` — plain text with `{{variable}}` placeholders. No templating engine. Orchestration (Step 2) does a direct string substitution pass.
```

With:

```
`llm/prompts/task_start.md` — plain text with `{{variable}}` placeholders. No templating engine. Services layer (Step 2) does a direct string substitution pass.
```

- [ ] **Step 2.5: Update CodeChunkEmbedding schema**

Replace the CodeChunkEmbedding model:

```prisma
model CodeChunkEmbedding {
  id          Int                         @id @default(autoincrement())
  repoId      Int
  repo        Repo                        @relation(fields: [repoId], references: [id], onDelete: Cascade)
  filePath    String
  startLine   Int
  endLine     Int
  content     String
  contentHash String
  embedding   Unsupported("vector(768)")?
  updatedAt   DateTime                    @updatedAt

  @@unique([repoId, filePath, startLine, endLine])
}
```

With:

```prisma
model CodeChunkEmbedding {
  id          Int                         @id @default(autoincrement())
  repoId      Int
  repo        Repo                        @relation(fields: [repoId], references: [id], onDelete: Cascade)
  filePath    String
  chunkIndex  Int
  content     String
  contentHash String
  embedding   Unsupported("vector(768)")?
  updatedAt   DateTime                    @updatedAt

  @@unique([repoId, filePath, chunkIndex])
}
```

- [ ] **Step 2.6: Update blast radius section**

Replace:

```
- The existing `bin` entry in `package.json` points to `./build/index.js` — this still holds after migration since `mcp/index.ts` compiles to `build/mcp/index.js`. The `bin` path needs updating to `./build/mcp/index.js`.
```

With:

```
- The existing `bin` entry in `package.json` points to `./build/index.js` — this still holds after migration since `interfaces/mcp/index.ts` compiles to `build/interfaces/mcp/index.js`. The `bin` path needs updating to `./build/interfaces/mcp/index.js`.
```

Replace:

```
- Top-level directory structure. Changing this post-Step 2 would require Orchestration refactoring.
```

With:

```
- Top-level directory structure. Changing this post-Step 2 would require services refactoring.
```

- [ ] **Step 2.7: Commit**

```bash
git add docs/superpowers/specs/2026-04-03-wizard-v2-step1-design.md
git commit -m "docs: align Step 1 design spec with SPEC_v8"
```

---

## Task 3: Step 1 Plan

**Files:**
- Modify: `docs/superpowers/plans/2026-04-03-wizard-v2-step1.md`

---

- [ ] **Step 3.1: Update header tech stack**

Replace:

```
**Tech Stack:** TypeScript (ESM, Node16), Yarn 4 (node-modules linker), Prisma (`prisma-client` generator with output to `generated/prisma`), pgvector via `pgvector/pgvector:pg16` Docker image, Vitest.
```

With:

```
**Tech Stack:** TypeScript (ESM, bundler), Yarn 4 (node-modules linker), Prisma (`prisma-client` generator with output to `generated/prisma`), pgvector via `pgvector/pgvector:pg16` Docker image, Vitest.
```

- [ ] **Step 3.2: Update header architecture**

Replace:

```
**Architecture:** Delete `src/` and restructure into the spec's top-level layered directories (`data/`, `mcp/`, `shared/`, `llm/`, `services/`, `integrations/`, `tests/`).
```

With:

```
**Architecture:** Delete `src/` and restructure into the spec's top-level layered directories (`data/`, `interfaces/`, `shared/`, `llm/`, `services/`, `integrations/`, `tests/`).
```

- [ ] **Step 3.3: Update file map — mcp paths**

In the file map table, replace all `mcp/index.ts` references with `interfaces/mcp/index.ts`. Specifically:

Replace `| Create | `mcp/index.ts`` with `| Create | `interfaces/mcp/index.ts``.
Replace `| Delete | `src/index.ts`                        | Replaced by `mcp/index.ts`` with `| Delete | `src/index.ts`                        | Replaced by `interfaces/mcp/index.ts``.

- [ ] **Step 3.4: Update Task 1 package.json bin path**

Replace:

```json
  "bin": "./build/mcp/index.js",
```

With:

```json
  "bin": "./build/interfaces/mcp/index.js",
```

- [ ] **Step 3.5: Update Task 1 build script**

Replace:

```json
    "build": "tsc && chmod 755 build/mcp/index.js",
```

With:

```json
    "build": "tsc && chmod 755 build/interfaces/mcp/index.js",
```

- [ ] **Step 3.6: Update Task 2 mkdir command**

Replace:

```bash
mkdir -p data/repositories mcp shared llm/prompts llm/adapters llm/schemas llm/packaging services integrations/notion tests/contracts tests/unit
```

With:

```bash
mkdir -p data/repositories interfaces/mcp interfaces/cli interfaces/plugin shared llm/prompts llm/adapters llm/schemas llm/packaging services integrations/notion tests/contracts tests/unit
```

- [ ] **Step 3.7: Update Task 2 mcp/index.ts creation**

Replace all references to `mcp/index.ts` in Task 2 with `interfaces/mcp/index.ts`. This includes the step title, file path comment in the code block, and the git add/commit command.

- [ ] **Step 3.8: Update all tsconfig snippets**

In every `tsconfig.json` code block in the file, make these replacements:

1. `"target": "ES2022"` → `"target": "ES2023"`
2. `"moduleResolution": "Node16"` → `"moduleResolution": "bundler"`
3. `"mcp/**/*.ts"` → `"interfaces/**/*.ts"`

- [ ] **Step 3.9: Update CodeChunkEmbedding in Prisma schema**

In Task 3's Prisma schema code block, replace the CodeChunkEmbedding model:

Replace:
```
  filePath    String
  startLine   Int
  endLine     Int
```

With:
```
  filePath    String
  chunkIndex  Int
```

Replace:
```
  @@unique([repoId, filePath, startLine, endLine])
```

With:
```
  @@unique([repoId, filePath, chunkIndex])
```

- [ ] **Step 3.10: Update git add commands**

Replace any `git add mcp/` with `git add interfaces/mcp/`.

- [ ] **Step 3.11: Commit**

```bash
git add docs/superpowers/plans/2026-04-03-wizard-v2-step1.md
git commit -m "docs: align Step 1 plan with SPEC_v8 — interfaces/, ES2023, chunkIndex"
```

---

## Task 4: Step 2 Plan — Major Rewrite

**Files:**
- Modify: `docs/superpowers/plans/2026-04-04-wizard-v2-step2.md`

This is the most changed file. The orchestrator layer is dissolved into services.

---

- [ ] **Step 4.1: Replace the title**

Replace:

```
# Wizard v2 Step 2 — Orchestration → Data → LLM Layer Implementation Plan
```

With:

```
# Wizard v2 Step 2 — Services Layer: Session Lifecycle & Workflow Execution
```

- [ ] **Step 4.2: Replace the goal paragraph**

Replace:

```
**Goal:** Build the Orchestration layer — variable injection, pre-flight check, session lifecycle, and workflow execution — and prove that the LLM layer is invoked with prepared context, pre-flight passes before invocation, and session state survives a simulated crash.
```

With:

```
**Goal:** Build the services layer — variable injection, pre-flight check, session lifecycle, and workflow execution as service functions — and prove that the LLM layer is invoked with prepared context, pre-flight passes before invocation, and session state survives a simulated crash.
```

- [ ] **Step 4.3: Replace the architecture paragraph**

Replace the entire `**Architecture:**` paragraph with:

```
**Architecture:** Each workflow is a service function. No separate orchestration layer. Pre-flight is a shared utility called at the start of every service function — not an interface concern. Services read context from Postgres, resolve skill template variables, run pre-flight (Postgres reachable + pgvector installed), and produce a formatted prompt for the LLM adapter. Session state is written to Postgres before any LLM invocation — making it crash-durable by design. Workflow definitions live in `core/workflows/`; services execute them, never define them. WorkflowRun audit trail is written inside service functions, before and after execution. Session has `meetingId` and `createdById` FKs for traceability. All IDs are `Int @id @default(autoincrement())`. The Prisma generator uses `"prisma-client"` with `output = "../generated/prisma"` — all imports from `../../generated/prisma/index.js`, not `@prisma/client`.
```

- [ ] **Step 4.4: Update tech stack**

Replace:

```
**Tech Stack:** TypeScript (ESM, Node16), Prisma (`prisma-client` generator, output `generated/prisma`), Vitest. No new dependencies beyond Step 1.
```

With:

```
**Tech Stack:** TypeScript (ESM, bundler), Prisma (`prisma-client` generator, output `generated/prisma`), Vitest. No new dependencies beyond Step 1.
```

- [ ] **Step 4.5: Delete the Serena spike prerequisite and Task 0**

Delete the entire block starting from:

```
> **PREREQUISITE — Serena Spike:**
```

Through the end of Task 0 (Step 0.4 commit). This includes the prerequisite note and all of Task 0's steps (0.1 through 0.4).

- [ ] **Step 4.6: Replace the file map table**

Replace:

```
| Action | Path                                              | Responsibility                                                             |
| ------ | ------------------------------------------------- | -------------------------------------------------------------------------- |
| Create | `orchestrator/inject.ts`                          | Variable injection — replaces `{{key}}` placeholders; throws on unresolved |
| Create | `orchestrator/preflight.ts`                       | Pre-flight check — Postgres reachable + pgvector installed                 |
| Create | `orchestrator/session.ts`                         | Session lifecycle — create, attach task, end, re-query                     |
| Create | `orchestrator/workflow.ts`                        | Workflow execution — runs task_start, returns formatted prompt             |
| Create | `core/workflows/task-start.ts`                    | Hardcoded task_start workflow definition                                   |
| Modify | `mcp/index.ts`                                    | Add `session_start` and `task_start` MCP tools                             |
| Modify | `tsconfig.json`                                   | Add `orchestrator/**/*.ts` and `core/**/*.ts` to `include`                 |
| Create | `tests/unit/inject.test.ts`                       | Unit test for `injectVariables` (migrated from inline test)                |
| Create | `tests/contracts/orchestration-to-llm.test.ts`    | Step 2 proof criteria                                                      |
```

With:

```
| Action | Path                                              | Responsibility                                                             |
| ------ | ------------------------------------------------- | -------------------------------------------------------------------------- |
| Create | `services/inject.ts`                              | Variable injection — replaces `{{key}}` placeholders; throws on unresolved |
| Create | `services/preflight.ts`                           | Pre-flight check — Postgres reachable + pgvector installed                 |
| Create | `services/session.ts`                             | Session lifecycle — create, attach task, end, re-query                     |
| Create | `services/workflow.ts`                            | Workflow execution — runs task_start, returns formatted prompt             |
| Create | `core/workflows/task-start.ts`                    | Hardcoded task_start workflow definition                                   |
| Modify | `interfaces/mcp/index.ts`                         | Add `session_start` and `task_start` MCP tools                             |
| Modify | `tsconfig.json`                                   | Add `core/**/*.ts` to `include` (`services/**/*.ts` already present)       |
| Create | `tests/unit/inject.test.ts`                       | Unit test for `injectVariables` (migrated from inline test)                |
| Create | `tests/contracts/services-to-llm.test.ts`         | Step 2 proof criteria                                                      |
```

- [ ] **Step 4.7: Global find-and-replace across the entire file**

Apply these replacements across the entire file:

1. `orchestrator/inject` → `services/inject` (all occurrences)
2. `orchestrator/preflight` → `services/preflight` (all occurrences)
3. `orchestrator/session` → `services/session` (all occurrences)
4. `orchestrator/workflow` → `services/workflow` (all occurrences)
5. `orchestrator/` → `services/` (any remaining directory references)
6. `orchestration-to-llm` → `services-to-llm` (test file name)
7. `mcp/index.ts` → `interfaces/mcp/index.ts` (all occurrences)
8. `"target": "ES2022"` → `"target": "ES2023"` (all occurrences)
9. `"moduleResolution": "Node16"` → `"moduleResolution": "bundler"` (all occurrences)
10. `"orchestrator/**/*.ts"` → (delete this line from tsconfig includes — `services/**/*.ts` already covers it)

- [ ] **Step 4.8: Renumber tasks**

With Task 0 removed, renumber:
- Task 1 → Task 1 (no change, was already Task 1)
- But update Task 1's title from referencing tsconfig for orchestrator to: "tsconfig.json — Add core/ Directory"
- In Task 1's mkdir command, replace `mkdir -p orchestrator core/workflows docs/spikes` with `mkdir -p core/workflows`
- Update commit messages throughout: `orchestrator` → `services`

- [ ] **Step 4.9: Update commit messages**

Replace all commit messages containing `orchestrator` with `services`. Examples:

- `"chore: add orchestrator/ and core/ to tsconfig"` → `"chore: add core/ to tsconfig"`
- `"feat: add injectVariables to orchestrator/inject"` → `"feat: add injectVariables to services/inject"`
- `"feat: add runPreflight to orchestrator/preflight"` → `"feat: add runPreflight to services/preflight"`

- [ ] **Step 4.10: Commit**

```bash
git add docs/superpowers/plans/2026-04-04-wizard-v2-step2.md
git commit -m "docs: rewrite Step 2 plan — orchestrator dissolved into services, Serena spike removed"
```

---

## Task 5: Step 3 Plan

**Files:**
- Modify: `docs/superpowers/plans/2026-04-04-wizard-v2-step3.md`

---

- [ ] **Step 5.1: Update the goal paragraph**

Replace any reference to custom PII scrubbing with Presidio. Replace:

```
**Goal:** Build the Security layer (PII scrubbing), the first integration (Notion), the config system (`wizard.config.yaml`), and the `wizard setup` CLI command. Prove that raw Notion data passes through PII scrubbing before reaching Postgres, and that an audit trail records what was scrubbed.
```

With:

```
**Goal:** Build the Security layer (PII scrubbing via Presidio Docker sidecar), the first integration (Notion), the config system (`wizard.config.yaml`), and the `wizard setup` CLI command. Prove that raw Notion data passes through PII scrubbing before reaching Postgres, and that an audit trail records what was scrubbed.
```

- [ ] **Step 5.2: Update the architecture paragraph**

Replace the PII description. Change:

```
The Security layer scrubs PII (emails, phone numbers, NHS numbers) and emits audit entries. It never stubs — detected PII is removed, not replaced.
```

With:

```
The Security layer scrubs PII via Microsoft Presidio (Docker HTTP sidecar) and emits audit entries. It never stubs — detected PII is removed, not replaced. Presidio provides 50+ built-in recognisers including emails, UK phone numbers, and NHS numbers. The TypeScript `security/` module is an HTTP client (~50 lines) calling the Presidio REST API.
```

- [ ] **Step 5.3: Update tech stack**

Replace:

```
**Tech Stack:** TypeScript (ESM, Node16), Prisma (`prisma-client` generator with output to `generated/prisma`), Vitest, `js-yaml` (YAML parsing), `commander` (CLI), `@notionhq/client` (already installed). Node's built-in `crypto` for AES-256-GCM token encryption. No new heavy dependencies.
```

With:

```
**Tech Stack:** TypeScript (ESM, bundler), Prisma (`prisma-client` generator with output to `generated/prisma`), Vitest, `js-yaml` (YAML parsing), `commander` (CLI), `@notionhq/client` (already installed). Node's built-in `crypto` for AES-256-GCM token encryption. Microsoft Presidio Docker sidecar for PII detection.
```

- [ ] **Step 5.4: Update file map — paths and PII approach**

In the file map table:

1. Replace `security/scrub.ts` description: `PII detection (regex) and removal; returns scrubbed text + audit entries` → `PII detection via Presidio HTTP client; returns scrubbed text + audit entries`
2. Replace `cli/index.ts` → `interfaces/cli/index.ts`
3. Replace `cli/commands/setup.ts` → `interfaces/cli/commands/setup.ts`

- [ ] **Step 5.5: Update all tsconfig snippets**

In every tsconfig code block:

1. `"target": "ES2022"` → `"target": "ES2023"`
2. `"moduleResolution": "Node16"` → `"moduleResolution": "bundler"`
3. Replace `"mcp/**/*.ts"` with `"interfaces/**/*.ts"`
4. Replace `"cli/**/*.ts"` → remove (covered by `"interfaces/**/*.ts"`)
5. Replace `"orchestrator/**/*.ts"` → remove (not needed)

- [ ] **Step 5.6: Update Task 1 mkdir command**

Replace:

```bash
mkdir -p security cli/commands data/repositories
```

With:

```bash
mkdir -p security interfaces/cli/commands data/repositories
```

- [ ] **Step 5.7: Rewrite Task 3 — PII scrubbing with Presidio**

Replace the custom regex-based `security/scrub.ts` implementation with a Presidio HTTP client. The test should verify PII is detected and removed via the Presidio sidecar (requires docker-compose up). Replace the entire `scrub.ts` code block with:

```typescript
// security/scrub.ts
import { createHash } from 'node:crypto'
import type { ScrubResult, AuditEntry } from './types.js'

const PRESIDIO_ANALYZER_URL = process.env.PRESIDIO_ANALYZER_URL ?? 'http://localhost:5002'
const PRESIDIO_ANONYMIZER_URL = process.env.PRESIDIO_ANONYMIZER_URL ?? 'http://localhost:5001'

type AnalyzerResult = {
  entity_type: string
  start: number
  end: number
  score: number
}

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}

/**
 * Detects and removes PII from a text string using Microsoft Presidio.
 * Returns the cleaned text and an audit entry for each match.
 * Scrub only — detected PII is removed, not stubbed or replaced.
 */
export async function scrub(text: string, fieldPath: string): Promise<ScrubResult> {
  // Step 1: Analyze — detect PII entities
  const analyzeResponse = await fetch(`${PRESIDIO_ANALYZER_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language: 'en' }),
  })

  if (!analyzeResponse.ok) {
    throw new Error(`Presidio analyzer error: ${analyzeResponse.status}`)
  }

  const entities: AnalyzerResult[] = await analyzeResponse.json()

  // Build audit entries from detected entities
  const entries: AuditEntry[] = entities.map((entity) => ({
    fieldPath,
    piiType: entity.entity_type.toLowerCase(),
    originalHash: sha256(text.slice(entity.start, entity.end)),
  }))

  if (entities.length === 0) {
    return { text, entries: [] }
  }

  // Step 2: Anonymize — remove detected PII
  const anonymizeResponse = await fetch(`${PRESIDIO_ANONYMIZER_URL}/anonymize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      analyzer_results: entities,
      anonymizers: { DEFAULT: { type: 'replace', new_value: '' } },
    }),
  })

  if (!anonymizeResponse.ok) {
    throw new Error(`Presidio anonymizer error: ${anonymizeResponse.status}`)
  }

  const result = await anonymizeResponse.json()
  const cleaned = (result.text as string).replace(/  +/g, ' ').trim()

  return { text: cleaned, entries }
}
```

Update `security/types.ts` to change `PiiType` from a union literal to `string` (Presidio returns many entity types):

```typescript
// security/types.ts
export type AuditEntry = {
  fieldPath: string
  piiType: string        // Presidio entity_type, lowercased
  originalHash: string   // SHA-256 hex of the original match
}

export type ScrubResult = {
  text: string           // cleaned text with PII removed
  entries: AuditEntry[]  // one entry per detected PII instance
}
```

Update the test to be async and require Presidio running:

```typescript
// tests/unit/scrub.test.ts
import { describe, it, expect } from 'vitest'
import { scrub } from '../../security/scrub.js'

// Requires: docker-compose up -d (Presidio sidecar must be running)
describe('scrub (Presidio)', () => {
  it('removes email addresses from text', async () => {
    const result = await scrub('Contact kiran@example.com for details', 'notion.meeting.notes')
    expect(result.text).not.toContain('kiran@example.com')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
    expect(result.entries[0].piiType).toContain('email')
  })

  it('removes UK phone numbers from text', async () => {
    const result = await scrub('Call +447700900123 to discuss', 'notion.task.description')
    expect(result.text).not.toContain('+447700900123')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
  })

  it('returns unchanged text when no PII is present', async () => {
    const input = 'Deploy the auth service to staging'
    const result = await scrub(input, 'notion.task.title')
    expect(result.text).toBe(input)
    expect(result.entries).toHaveLength(0)
  })

  it('stores a SHA-256 hash of the original match', async () => {
    const result = await scrub('Contact dev@example.com', 'test.field')
    if (result.entries.length > 0) {
      expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)
    }
  })
})
```

- [ ] **Step 5.8: Update docker-compose references**

Where the plan mentions docker-compose or `wizard setup`, add Presidio services. Add a note that `docker-compose.yaml` should include:

```yaml
  presidio-analyzer:
    image: mcr.microsoft.com/presidio-analyzer:latest
    ports:
      - "5002:5002"

  presidio-anonymizer:
    image: mcr.microsoft.com/presidio-anonymizer:latest
    ports:
      - "5001:5001"
```

- [ ] **Step 5.9: Update all `cli/` paths to `interfaces/cli/`**

Replace all occurrences:
- `cli/index.ts` → `interfaces/cli/index.ts`
- `cli/commands/setup.ts` → `interfaces/cli/commands/setup.ts`
- `build/cli/index.js` → `build/interfaces/cli/index.js`

- [ ] **Step 5.10: Update .env.example references**

Add Presidio URLs:

```
PRESIDIO_ANALYZER_URL=http://localhost:5002
PRESIDIO_ANONYMIZER_URL=http://localhost:5001
```

- [ ] **Step 5.11: Commit**

```bash
git add docs/superpowers/plans/2026-04-04-wizard-v2-step3.md
git commit -m "docs: align Step 3 plan with SPEC_v8 — Presidio sidecar, interfaces/"
```

---

## Task 6: Step 4 Plan

**Files:**
- Modify: `docs/superpowers/plans/2026-04-04-wizard-v2-step4.md`

---

- [ ] **Step 6.1: Update tech stack**

Replace:

```
**Tech Stack:** TypeScript (ESM, Node16), Prisma (generator `"prisma-client"`, output `"../generated/prisma"`), Vitest, `pgvector` npm package
```

With:

```
**Tech Stack:** TypeScript (ESM, bundler), Prisma (generator `"prisma-client"`, output `"../generated/prisma"`), Vitest, `pgvector` npm package
```

- [ ] **Step 6.2: Add materialise step to pipeline description**

In the architecture/goal section, where the pipeline is described as `process → transform → validate → store`, replace with `process → transform → validate → store → materialise`.

Add after the store step description:

```
(5) `materialise` — for skills flagged `materialise: true` in `core/`, create a Note entity (investigation or decision type), link to current Task and Session, trigger embedding. One function, not a framework. Note creation failure is logged but does not fail the pipeline.
```

- [ ] **Step 6.3: Update all tsconfig snippets**

1. `"target": "ES2022"` → `"target": "ES2023"`
2. `"moduleResolution": "Node16"` → `"moduleResolution": "bundler"`

- [ ] **Step 6.4: Replace orchestrator references**

Any remaining references to `orchestrator` in the file should be replaced with `services`. Check for:
- "Orchestration writes a FAILED WorkflowRun" → "Service function writes a FAILED WorkflowRun"
- Any `orchestrator/` paths → `services/`

- [ ] **Step 6.5: Replace mcp/ paths**

Replace any `mcp/` path references with `interfaces/mcp/`.

- [ ] **Step 6.6: Commit**

```bash
git add docs/superpowers/plans/2026-04-04-wizard-v2-step4.md
git commit -m "docs: align Step 4 plan with SPEC_v8 — materialise step, ES2023, services"
```

---

## Task 7: Step 5 Plan

**Files:**
- Modify: `docs/superpowers/plans/2026-04-04-wizard-v2-step5.md`

---

- [ ] **Step 7.1: Update the goal paragraph**

Remove "a second LLM adapter (model-agnostic proof)" from the goal. Replace:

```
**Goal:** Build remaining integrations (Jira, Krisp, GitHub, Serena), task-type aware context loading, the full session flow (`wizard session start` → `wizard session end`), remaining CLI commands, remaining skill templates in `llm/prompts/`, `llm/packaging/` rendering into model-specific install formats, evaluation scaffolding in `evals/`, and a second LLM adapter (model-agnostic proof). Prove the full session runs end-to-end with PII-free Postgres, task-type specific context, and traceable output.
```

With:

```
**Goal:** Build remaining integrations (Jira, Krisp, GitHub), task-type aware context loading, CodeChunkEmbedding with chunking strategy, the full session flow (`wizard session start` → `wizard session end`), remaining CLI commands, remaining skill templates in `llm/prompts/`, `llm/packaging/` rendering into model-specific install formats, and evaluation scaffolding in `evals/`. Prove the full session runs end-to-end with PII-free Postgres, task-type specific context, and traceable output.
```

- [ ] **Step 7.2: Update the architecture paragraph**

Remove Serena references. Replace "Each integration follows the same pattern as Notion" section to remove Serena mention. Remove "Serena" from the architecture description entirely.

- [ ] **Step 7.3: Update tech stack**

Replace:

```
**Tech Stack:** TypeScript (ESM, Node16)
```

With:

```
**Tech Stack:** TypeScript (ESM, bundler)
```

Add `@langchain/textsplitters` to the new dependencies list.

- [ ] **Step 7.4: Update file map — remove Serena and OpenAI**

Remove these rows from the file map:

```
| Create | `integrations/serena/invoke.ts` | Deterministic Serena invocation (uses spike result from Step 2) |
| Create | `llm/adapters/openai.ts` | Second LLM adapter — model-agnostic proof |
| Create | `tests/contracts/llm-adapter-openai.test.ts` | Second adapter passes same contract as Ollama adapter |
```

- [ ] **Step 7.5: Update file map — add CodeChunkEmbedding files**

Add to file map:

```
| Create | `services/code-chunker.ts` | Chunks code files using @langchain/textsplitters RecursiveCharacterTextSplitter (512 tokens, 256 overlap) |
| Create | `tests/unit/code-chunker.test.ts` | Chunking produces correct chunkIndex, contentHash |
```

- [ ] **Step 7.6: Update file map — cli paths**

Replace all `cli/` paths with `interfaces/cli/`:
- `cli/commands/session.ts` → `interfaces/cli/commands/session.ts`
- `cli/commands/task.ts` → `interfaces/cli/commands/task.ts`
- `cli/commands/doctor.ts` → `interfaces/cli/commands/doctor.ts`
- `cli/commands/integrate.ts` → `interfaces/cli/commands/integrate.ts`
- `cli/index.ts` → `interfaces/cli/index.ts`

- [ ] **Step 7.7: Update Task 1 dependencies**

Add `@langchain/textsplitters` to the install command:

```bash
yarn add @octokit/rest @langchain/textsplitters
```

- [ ] **Step 7.8: Update Task 1 mkdir command**

Remove `integrations/serena` from the mkdir command. Replace:

```bash
mkdir -p integrations/jira integrations/krisp integrations/github integrations/serena evals llm/prompts llm/adapters llm/packaging/targets services
```

With:

```bash
mkdir -p integrations/jira integrations/krisp integrations/github evals llm/prompts llm/adapters llm/packaging/targets services
```

- [ ] **Step 7.9: Remove Serena from Task 2**

Delete Step 2.4 (`integrations/serena/invoke.ts`) and its entire code block. Update the commit command to remove `integrations/serena/invoke.ts`:

Replace:
```bash
git add integrations/jira/pull.ts integrations/krisp/pull.ts integrations/github/pull.ts integrations/serena/invoke.ts
git commit -m "feat: add Jira, Krisp, GitHub, and Serena integrations"
```

With:
```bash
git add integrations/jira/pull.ts integrations/krisp/pull.ts integrations/github/pull.ts
git commit -m "feat: add Jira, Krisp, and GitHub integrations"
```

- [ ] **Step 7.10: Update Task 3 context loader — remove Serena**

In the context loader task:
- Remove `vi.mock('../../integrations/serena/invoke.js'` from test mocks
- Remove `import { findSymbol } from '../../integrations/serena/invoke.js'` from implementation
- Remove `serenaSymbols` from the context type and implementation
- Remove Serena from CODING, DEBUGGING, INVESTIGATION, TEST_GENERATION task type context loading
- Update test expectations that reference Serena

- [ ] **Step 7.11: Delete Task 8 (Second LLM Adapter)**

Delete the entire Task 8 section including:
- `llm/adapters/openai.ts` code block
- `tests/contracts/llm-adapter-openai.test.ts` code block
- All steps 8.1 through 8.6

- [ ] **Step 7.12: Update all tsconfig snippets**

In every tsconfig code block:
1. `"target": "ES2022"` → `"target": "ES2023"`
2. `"moduleResolution": "Node16"` → `"moduleResolution": "bundler"`
3. Replace `"mcp/**/*.ts"` → `"interfaces/**/*.ts"`
4. Replace `"cli/**/*.ts"` → remove (covered by `"interfaces/**/*.ts"`)
5. Replace `"orchestrator/**/*.ts"` → remove (not needed)

- [ ] **Step 7.13: Update verification/troubleshooting**

Remove any references to:
- Serena connection errors or `SERENA_COMMAND`
- OpenAI adapter tests
- "Second adapter" verification

Update the final verification checklist to reflect no Serena and no OpenAI adapter.

- [ ] **Step 7.14: Update all `cli/` paths in code blocks**

Replace all `cli/` references in code blocks and git commands:
- `build/cli/index.js` → `build/interfaces/cli/index.js`
- `cli/index.ts` → `interfaces/cli/index.ts`
- `cli/commands/` → `interfaces/cli/commands/`

- [ ] **Step 7.15: Commit**

```bash
git add docs/superpowers/plans/2026-04-04-wizard-v2-step5.md
git commit -m "docs: align Step 5 plan with SPEC_v8 — remove Serena/OpenAI, add chunking, interfaces/"
```

---

## Task 8: Verification

- [ ] **Step 8.1: Run verification grep checks**

```bash
# No orchestrator/ directory references remain (except in spec-v8-alignment docs which describe the change)
grep -rn 'orchestrator/' AGENTS.md docs/superpowers/plans/ docs/superpowers/specs/2026-04-03-wizard-v2-step1-design.md

# No bare mcp/ paths (should be interfaces/mcp/)
grep -rn '"mcp/' AGENTS.md docs/superpowers/plans/ docs/superpowers/specs/2026-04-03-wizard-v2-step1-design.md

# No ES2022 in tsconfig blocks
grep -rn 'ES2022' docs/superpowers/plans/

# No startLine/endLine in CodeChunkEmbedding
grep -rn 'startLine\|endLine' docs/superpowers/plans/ docs/superpowers/specs/2026-04-03-wizard-v2-step1-design.md

# No Serena in plans (except step5 where it's removed from file map)
grep -rn 'serena\|Serena' docs/superpowers/plans/2026-04-04-wizard-v2-step2.md docs/superpowers/plans/2026-04-04-wizard-v2-step3.md docs/superpowers/plans/2026-04-04-wizard-v2-step4.md

# No OpenAI adapter references
grep -rn 'openai\.ts\|OpenAIAdapter\|llm-adapter-openai' docs/superpowers/plans/
```

Expected: all grep commands return empty (zero matches).

- [ ] **Step 8.2: Commit the alignment design doc update if needed**

If verification found issues that were fixed, commit the fixes:

```bash
git add -A docs/superpowers/ AGENTS.md
git commit -m "docs: fix remaining SPEC_v8 alignment issues found in verification"
```
