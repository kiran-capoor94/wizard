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
yarn test tests/contracts/data-to-mcp.test.ts   # single test file
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
├── data/           # Postgres + pgvector — Prisma schema, migrations, queries
├── mcp/            # MCP server — exposes Wizard capabilities to Claude
├── cli/            # Human interface — wizard commands (planned)
├── shared/         # Shared types and constants only — NO business logic
├── core/           # Business/domain logic — workflows, prompt templates, rules
├── orchestrator/   # Workflow execution, session lifecycle, DB sync (planned)
├── security/       # PII detection and scrubbing (planned)
├── integrations/   # Notion, Jira, Krisp, Serena, GitHub — external connections
├── plugin/         # Claude interface — skills and prompts as templates
├── evals/          # Eval scaffolding — dataset format, runner stub (planned)
└── tests/
    ├── contracts/  # Contract tests at every layer boundary
    └── unit/       # Unit tests — variable injection, pipeline ordering, PII
```

Key distinctions:
- `plugin/` defines skills/prompts. `orchestrator/` injects variables at runtime.
- `core/` defines workflows. `orchestrator/` executes them.
- `shared/` is types and constants only. Never business logic.
- `evals/` is a dev tool, not part of the system.

## Architecture Principles

1. Claude owns reasoning and synthesis only. Everything else is deterministic.
2. Each layer has one responsibility. Encroachment means a new layer.
3. Postgres is the single source of truth. All other stores are derived.
4. Complexity must be justified by an observed problem, not an anticipated one.
5. Local-first. No hosting, no multi-tenancy.
6. PII never reaches Claude or Postgres in raw form.
7. Prefer reversible decisions. Name irreversible ones explicitly.

Dependency flow: `Integration → Security → Data ← Orchestration → Claude → Data`

## Code Style

### TypeScript
- **Strict mode** always. No `any` unless explicitly justified.
- **ESM** with `Node16` module resolution. Use `.js` extensions in imports.
- **Target**: ES2022.

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
- `TaskContext` is the canonical type for what Claude receives.
- Optional fields use `| null` (not `undefined`) — matches Prisma defaults.
- Return `Promise<T | null>` for queries that may find nothing.

### Error Handling
- **Errors as values**: no throws in domain code — return structured results.
- MCP tools return `{ content: [...], isError: true }` for failures.
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
| 1 | Postgres schema, pgvector, MCP, first skill | Contract test: Claude receives exactly what Postgres contains |
| 2 | Orchestration, session lifecycle, pre-flight | Claude invoked by Orchestration with prepared context |
| 3 | First integration (Notion), PII scrubbing, config | Raw data enters, PII removed, clean data reaches Claude |
| 4 | Claude output pipeline: process → transform → validate → store | Invalid output rejected, correct output retrievable |
| 5 | All integrations, task-type context, CLI, evals | Full session flow end-to-end |

Current status: **Step 1 in progress** — plan defined, not yet built.

## Tech Stack

- TypeScript (ESM, strict, Node16)
- Yarn 4 (node-modules linker)
- Prisma + Postgres + pgvector
- Vitest (test runner)
- @modelcontextprotocol/sdk (MCP server)
- Zod (validation)
- Docker Compose (local Postgres)
