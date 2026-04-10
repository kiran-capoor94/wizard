# AGENTS.md — Wizard v2

AI-Powered Engineering Workflow System. Local-first. TypeScript.

## Commands

### Build & Type Check

```bash
yarn build          # tsc + chmod
yarn tsc --noEmit   # type check only (alias: tsc --noEmit)
```

### Test

```bash
yarn test                    # run all tests (vitest run)
yarn test:watch              # vitest watch mode
yarn test tests/contracts/llm-adapter.test.ts   # single test file
yarn test -t "returns null"  # single test by name pattern
```

### Database

```bash
docker-compose up -d                              # start Postgres + pgvector
npx prisma migrate dev --name <name>              # create + apply migration
npx prisma validate                               # validate schema
npx prisma generate                               # regenerate client
docker-compose exec postgres psql -U wizard -d wizard  # psql shell
```

### Dependencies

```bash
yarn install    # install (Yarn 4, node-modules linker — NOT PnP)
yarn add <pkg>  # add dependency
```

## Project Structure

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

Key distinctions:

- `llm/prompts/` defines skills. `services/` injects variables at runtime.
- `core/` declares workflows. `services/` executes them.
- `data/` owns repositories. Services call repositories, never Postgres directly.
- `llm/adapters/` has two independent interfaces: `LLMAdapter` (generate) and `EmbeddingAdapter` (embed).
- `services/` owns context assembly, workflow execution, session lifecycle, and pre-flight.
- `shared/` is types and constants only. Never business logic.
- `evals/` is a dev tool, not part of the system.

## Architecture Principles

1. The LLM layer owns reasoning and synthesis only. Everything else is deterministic.
2. Each layer has one responsibility. Encroachment means a new layer.
3. Postgres is the single source of truth. All other stores are derived.
4. Complexity must be justified by an observed problem, not an anticipated one.
5. Local-first. No hosting, no multi-tenancy.
6. PII never reaches the LLM layer or Postgres in raw form.
7. Prefer reversible decisions. Name irreversible ones explicitly.

Dependency flow: `Integration → Security → Data ← Services → Output Pipeline → Data`

## Code Style

### TypeScript

- **Strict mode** always. No `any` unless explicitly justified.
- **ESM** with `bundler` module resolution. Use `.js` extensions in imports.
- **Target**: ES2023.

### Imports

- Use `.js` extensions in all import paths (even for `.ts` files).
- Group: external packages → internal modules (blank line between groups).
- Re-export Prisma enums from `shared/types.ts` — never re-declare.

### Naming

- `camelCase` for variables and functions
- `PascalCase` for classes, types, and interfaces
- `kebab-case` for file names
- `UPPER_SNAKE_CASE` for constants

### Formatting

- 2-space indentation (see `.editorconfig`)
- LF line endings, UTF-8, trailing newline
- Semicolons where TypeScript requires them

### Types

- Enums come from `@prisma/client` — single source of truth is the schema.
  - `TaskStatus` (TODO, IN_PROGRESS, DONE, BLOCKED), `TaskType`, `TaskPriority`, `SessionStatus`, `WorkflowStatus`, `NoteType`, `NoteParent`, `RepoProvider`
  - Re-export Prisma enums from `shared/types.ts` — never re-declare.
- `TaskContext` is the canonical type for what the LLM layer receives.
  - Includes `externalTaskId`, `branch`, `repoId`, and other fields from the Prisma `Task` model.
- IDs are integers (`@id @default(autoincrement())`), not strings (cuid).
- Optional fields use `| null` (not `undefined`) — matches Prisma defaults.
- Return `Promise<T | null>` for queries that may find nothing.

### Error Handling

- **Errors as values**: no throws in domain code — return structured results.
- LLM adapter errors return structured results with error type and traceId.
- Contract tests assert `null` (not `undefined` or `""`) for missing data.

### Testing

- **TDD** on domain logic and business rules. Red → Green → Refactor.
- Tests verify behaviour, not code paths.
- Contract tests live in `tests/contracts/` — prove layer boundaries.
- Unit tests live in `tests/unit/` — variable injection, pipeline ordering.
- Tests require Postgres running (`docker-compose up -d`).
- Teardown: delete seeded records in reverse FK order.

## Invariants (from owner's CLAUDE.md)

- **SRP**: One thing per function/module/class/service.
- **SLAP**: One level of abstraction per function.
- **DRY**: No duplicated logic. But don't over-abstract — two honest copies beat coupled shared code.
- **YAGNI**: Build what's needed now. Don't build for hypothetical futures.
- **Explicit over implicit**: Comments explain why, never what.
- **Blast radius before code**: State what this affects and what breaks if wrong before writing.
- **Plan before implement**: Show approach. Confirm. Then execute.

## Build Sequence

Built in 5 sequential steps. Each proves a contract before the next adds complexity.

| Step | Build | Proof |
|------|-------|-------|
| 1 | Postgres schema, pgvector, repositories, services, first skill | Contract test: LLM layer receives exactly what Postgres contains |
| 2 | Services layer with session lifecycle, workflow execution, pre-flight | LLM invoked by service function with prepared context |
| 3 | First integration (Notion), PII scrubbing via Presidio, config | Raw data enters, PII removed, clean data reaches LLM |
| 4 | LLM output pipeline: process → transform → validate → store → materialise | Invalid output rejected, correct output retrievable |
| 5 | All integrations, task-type context, CodeChunkEmbedding, CLI, evals | Full session flow end-to-end |

Current status: **Step 5 not started** — Steps 1-4 complete. Step 4 (LLM output pipeline) proved: valid output stored and retrievable, invalid output rejected, wrong attribution detected via pgvector.

## Tech Stack

- TypeScript (ESM, strict, bundler)
- Yarn 4 (node-modules linker)
- Prisma + Postgres + pgvector
- Ollama (embeddings: nomic-embed-text, vector(768))
- Vitest (test runner)
- Zod (validation)
- Docker Compose (local Postgres)
