# Wizard v2 — Step 1 Design: Data → Claude

| Field | Value |
|---|---|
| Date | 2026-04-03 |
| Author | Kiran Capoor |
| Step | 1 of 5 |
| Status | Approved |

---

## Context

Wizard v2 is built in five sequential steps, each proving a contract before the next layer adds complexity. This document covers Step 1 only.

**Step 1 goal**: Establish the data foundation and prove that Claude receives exactly what Postgres contains — type-checked and complete.

**What this step does not include**: Orchestration, integrations, security/PII scrubbing, CLI, or the full session flow. Those are Steps 2–5.

**Proof criteria**: A contract test asserting Claude receives exactly what Postgres contains for a given query — type-checked and complete. Not just that something is returned.

---

## Directory Structure

`src/` is deleted and replaced with the spec's top-level layered structure. `tsconfig.json` is updated to compile from the project root.

```
wizard/
├── data/
│   ├── prisma/
│   │   ├── schema.prisma
│   │   └── migrations/
│   └── queries/
│       └── index.ts          # typed query functions
├── mcp/
│   └── index.ts              # MCP server (migrated from src/index.ts)
├── plugin/
│   └── skills/
│       └── task_start.md     # first skill template
├── shared/
│   └── types.ts              # shared types and enums
├── integrations/
│   └── notion/
│       └── index.ts          # moved from src/notion/ (untouched, Step 3 concern)
├── tests/
│   └── contracts/
│       └── data-to-mcp.test.ts
├── docker-compose.yaml
├── tsconfig.json
└── package.json
```

**Files deleted**: `src/middleware.ts`, `src/tools/attention-list.ts` (empty stubs with no content).

**tsconfig.json changes**:
- `rootDir`: `.` (was `./src`)
- `include`: explicit list — `data/**/*.ts`, `mcp/**/*.ts`, `plugin/**/*.ts`, `shared/**/*.ts`, `integrations/**/*.ts` (excludes `tests/` from the production build; tests use a separate config or Vitest's own resolution)

---

## Prisma Schema

Full schema covering all entities named in the spec. pgvector extension enabled. Embedding table present but unpopulated — vector ops are a later-step concern.

### Enums

```prisma
enum TaskStatus {
  TODO
  IN_PROGRESS
  DONE
}

enum TaskType {
  CODING
  DEBUGGING
  INVESTIGATION
  ADR
  TEST_GENERATION
  MEETING_REVIEW
}

enum Priority {
  LOW
  MEDIUM
  HIGH
}

enum SessionStatus {
  ACTIVE
  ENDED
}

enum WorkflowStatus {
  PENDING
  RUNNING
  COMPLETED
  FAILED
}
```

### Models

```prisma
model Task {
  id           String        @id @default(cuid())
  title        String
  description  String?
  status       TaskStatus    @default(TODO)
  priority     Priority?
  dueDate      DateTime?
  taskType     TaskType
  jiraKey      String?
  githubBranch String?
  githubRepo   String?
  meetingId    String?
  meeting      Meeting?      @relation(fields: [meetingId], references: [id])
  sessions     SessionTask[]
  embedding    TaskEmbedding?
  createdAt    DateTime      @default(now())
  updatedAt    DateTime      @updatedAt
}

model Session {
  id            String        @id @default(cuid())
  status        SessionStatus @default(ACTIVE)
  workflowState Json?
  startedAt     DateTime      @default(now())
  endedAt       DateTime?
  tasks         SessionTask[]
  createdAt     DateTime      @default(now())
  updatedAt     DateTime      @updatedAt
}

model SessionTask {
  sessionId String
  taskId    String
  session   Session @relation(fields: [sessionId], references: [id])
  task      Task    @relation(fields: [taskId], references: [id])

  @@id([sessionId, taskId])
}

model Meeting {
  id          String   @id @default(cuid())
  title       String
  outline     String?
  keyPoints   String[]
  actionItems String[]
  krispUrl    String?
  notionUrl   String?
  tasks       Task[]
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
}

model IntegrationConfig {
  id        String   @id @default(cuid())
  source    String   @unique
  token     String   // ciphertext only — encryption/decryption in query layer
  metadata  Json?
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model WorkflowRun {
  id          String         @id @default(cuid())
  workflowId  String
  sessionId   String?
  taskId      String?
  status      WorkflowStatus @default(PENDING)
  input       Json?
  output      Json?
  startedAt   DateTime       @default(now())
  completedAt DateTime?
  createdAt   DateTime       @default(now())
  updatedAt   DateTime       @updatedAt
}

model CalibrationExample {
  id         String   @id @default(cuid())
  taskId     String?
  meetingId  String?
  label      Boolean  // true = correct link, false = wrong link
  similarity Float?   // populated after calibration run
  createdAt  DateTime @default(now())
}

model SemanticConfig {
  id        String   @id @default(cuid())
  key       String   @unique
  value     Float
  updatedAt DateTime @updatedAt
}

// pgvector — embedding table, populated in later steps
model TaskEmbedding {
  id        String                      @id @default(cuid())
  taskId    String                      @unique
  task      Task                        @relation(fields: [taskId], references: [id], onDelete: Cascade)
  embedding Unsupported("vector(1536)")?
}
```

**pgvector setup**: The first migration includes `CREATE EXTENSION IF NOT EXISTS vector;` as a raw SQL statement. All vector queries use Prisma's `$queryRaw` — no ORM abstraction over vector operations.

---

## MCP Interface

One tool registered in Step 1: **`get_task_context`**.

```
Input:  { task_id: string }
Output: TaskContext (see shared/types.ts)
```

**Call chain**:
```
mcp/index.ts
  → data/queries/index.ts :: getTaskContext(taskId)
  → Prisma Client
  → Postgres
```

`getTaskContext` returns a `TaskContext` — the typed contract between the data layer and Claude. It includes the full task with its linked meeting (if any), Jira key, GitHub branch/repo, and status.

### shared/types.ts — TaskContext

```typescript
// Re-export Prisma enums — single source of truth, stays in sync with schema
export { TaskStatus, Priority, TaskType } from '@prisma/client'

export type TaskContext = {
  id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: Priority | null
  dueDate: Date | null
  taskType: TaskType
  jiraKey: string | null
  githubBranch: string | null
  githubRepo: string | null
  meeting: {
    id: string
    title: string
    outline: string | null
    keyPoints: string[]
    actionItems: string[]
    krispUrl: string | null
  } | null
}
```

`TaskContext` is the canonical type for what Claude receives. Enums are re-exported from `@prisma/client` — never re-declared. This keeps `shared/types.ts` in sync with the schema automatically. It is imported by both `data/queries/` (to type the return) and `mcp/` (to type the tool response). Any schema change that affects what Claude sees must change `TaskContext` first.

---

## Skill Template

`plugin/skills/task_start.md` — plain text with `{{variable}}` placeholders. No templating engine. Orchestration (Step 2) does a direct string substitution pass. Unresolved placeholders are a hard error, not silent pass-through.

```
Task: {{title}} ({{task_id}})
Type: {{task_type}} | Status: {{status}}
Jira: {{jira_key}}
Due: {{due_date}}

Context:
{{context}}
```

**Variables for `task_start`**:

| Variable | Source | Type |
|---|---|---|
| `{{task_id}}` | TaskContext.id | string |
| `{{title}}` | TaskContext.title | string |
| `{{task_type}}` | TaskContext.taskType | TaskType enum |
| `{{status}}` | TaskContext.status | TaskStatus enum |
| `{{jira_key}}` | TaskContext.jiraKey | string \| null |
| `{{due_date}}` | TaskContext.dueDate | Date \| null |
| `{{context}}` | Serialised TaskContext | JSON string |

Unit test: given a valid `TaskContext`, every `{{variable}}` in the template is replaced. Any unresolved placeholder in the output causes the test to fail.

---

## Contract Test

**File**: `tests/contracts/data-to-mcp.test.ts`
**Runner**: Vitest
**Requires**: Postgres running (docker-compose)

```
1. Seed: insert a Meeting + Task to Postgres via Prisma
2. Call: getTaskContext(task.id) directly
3. Assert: every field in the returned TaskContext matches the seed
         — correct types, no missing fields, no extra fields
4. Teardown: delete seeded records (in reverse FK order)
```

The test does not go through the MCP wire protocol — it calls the query function directly. The MCP tool is a thin wrapper; the contract is at the query layer.

**What "type-checked and complete" means in practice**:
- `title` is a string matching the seeded string exactly
- `dueDate` is a `Date` object (not a string)
- `meeting` is non-null and its fields match the seeded meeting
- `jiraKey` is `null` when not set (not `undefined`, not `""`)

---

## Docker

```yaml
# docker-compose.yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: wizard
      POSTGRES_USER: wizard
      POSTGRES_PASSWORD: wizard
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

`DATABASE_URL` in `.env`: `postgresql://wizard:wizard@localhost:5432/wizard`

---

## New Dependencies

| Package | Type | Purpose |
|---|---|---|
| `prisma` | dev | CLI — migrations, schema generation |
| `@prisma/client` | prod | Generated type-safe client |
| `vitest` | dev | Test runner for contract and unit tests |
| `pgvector` | dev | Placeholder — not actively used in Step 1. Added now so Step 4 (vector validation) doesn't require a dependency install mid-build. |

---

## Blast Radius

**What this step touches**:
- Deletes `src/` entirely (3 files, all stubs or near-stubs)
- Rewrites `tsconfig.json` (rootDir + include)
- Adds `docker-compose.yaml`, `data/`, `mcp/`, `plugin/`, `shared/`, `integrations/`, `tests/`
- Adds Prisma to `package.json`

**What could break**:
- The existing `bin` entry in `package.json` points to `./build/index.js` — this still holds after migration since `mcp/index.ts` compiles to `build/mcp/index.js`. The `bin` path needs updating to `./build/mcp/index.js`.
- `.claude-plugin/plugin.json` has no path dependency — unaffected.

**Irreversible decisions in this step**:
- Committing to Prisma as the query layer. Migration away later would require rewriting `data/queries/` and all migrations.
- Top-level directory structure. Changing this post-Step 2 would require Orchestration refactoring.

---

## Verification

Step 1 is complete when:

1. `docker-compose up -d` starts Postgres with pgvector
2. `prisma migrate dev` applies the schema without error
3. `npx vitest run tests/contracts/data-to-mcp.test.ts` passes — seeded data returned type-checked and complete
4. `npx vitest run tests/unit/` passes — skill variable injection resolves all placeholders
5. `tsc --noEmit` passes with zero errors
