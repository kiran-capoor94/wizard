# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Wizard

Wizard is a local-first, AI-powered engineering workflow system. It orchestrates LLM-driven skills (meeting review, code investigation, etc.) over a Postgres + pgvector backend. Currently in early build — Step 3 of 5 is in progress.

## Commands

```bash
yarn test                              # run all tests (vitest)
yarn test tests/contracts/llm-adapter.test.ts  # single file
yarn test -t "returns null"            # single test by name
yarn test:watch                        # vitest watch mode
yarn build                             # tsc + chmod
yarn tsc --noEmit                      # type check only
```

### Database

```bash
docker-compose up -d                   # start Postgres + pgvector
npx prisma migrate dev --name <name>   # create + apply migration
npx prisma generate                    # regenerate client
npx prisma validate                    # validate schema
```

Database URL is read from `.env` (`DATABASE_URL`). Default docker-compose creds: `wizard/wizard/wizard` on port 5432.

## Architecture

See `AGENTS.md` for the full project structure and architecture principles — it is the canonical reference. Key points:

- **Dependency flow**: Integration → Security → Data ← Orchestration → LLM Layer → Data
- **Prisma is the enum source of truth** — re-export from `shared/types.ts`, never redeclare
- **IDs are autoincrement integers**, not cuid/uuid
- **Optional fields use `| null`** (not `undefined`) to match Prisma
- **Errors as values** — no throws in domain code, return structured results
- **LLM adapters** have two independent interfaces: `BaseLLMAdapter` (generate) and `EmbeddingAdapter` (embed)
- **`AbstractLLMAdapter`** provides `safeParse` (strips markdown fences from JSON) and `validate` (Zod) helpers
- Prisma client is generated to `generated/prisma/` (gitignored)
- Embedding dimension is `vector(768)` (nomic-embed-text via Ollama)

## Code Style

- **ESM** with `.js` extensions in all import paths (even for `.ts` source files)
- **Strict TypeScript**, no `any` unless justified
- Target ES2023, moduleResolution `bundler`
- 2-space indent, LF line endings, semicolons where TS requires
- `camelCase` vars/functions, `PascalCase` types/classes, `kebab-case` files, `UPPER_SNAKE_CASE` constants
- Vitest for testing. Contract tests in `tests/contracts/`, unit tests in `tests/unit/`
- No vitest config file — uses defaults with ESM

## Build Sequence

The system is built in 5 sequential steps (see `AGENTS.md` and `docs/superpowers/plans/` for details). Each step proves a contract before the next begins. Steps 1 and 2 are complete. Step 3 (security, integrations, CLI) is in progress.
