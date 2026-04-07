# Wizard v2 — Step 1 Design: Data → LLM Layer

| Field | Value |
|---|---|
| Date | 2026-04-03 |
| Author | Kiran Capoor |
| Step | 1 of 5 |
| Status | Approved |

---

## Context

Wizard v2 is built in five sequential steps, each proving a contract before the next layer adds complexity. This document covers Step 1 only.

**Step 1 goal**: Establish the data foundation and prove that the LLM layer receives exactly what Postgres contains — type-checked and complete.

**What this step does not include**: Orchestration, integrations, security/PII scrubbing, CLI, or the full session flow. Those are Steps 2–5.

**Proof criteria**: A contract test asserting the LLM layer receives exactly what Postgres contains for a given query — type-checked and complete. Not just that something is returned.

---

## Directory Structure

`src/` is deleted and replaced with the spec's top-level layered structure. `tsconfig.json` is updated to compile from the project root.

```
wizard/
├── data/
│   ├── prisma/
│   │   ├── schema.prisma
│   │   └── migrations/
│   └── repositories/
│       └── task.ts            # typed repository functions
├── interfaces/
│   ├── mcp/
│   │   └── index.ts           # MCP server (migrated from src/index.ts)
│   ├── cli/                   # Placeholder — Step 3
│   └── plugin/                # Placeholder — Step 5
├── llm/
│   ├── adapters/              # LLM + Embedding adapters (model-specific clients)
│   ├── prompts/
│   │   └── task_start.md      # first skill template
│   ├── schemas/               # I/O contracts and validators
│   └── packaging/             # Renders templates to model-specific install formats
├── services/
│   └── index.ts               # Context assembly (calls repositories, builds LLM context)
├── shared/
│   └── types.ts               # shared types and enums
├── integrations/
│   └── notion/
│       └── index.ts           # moved from src/notion/ (untouched, Step 3 concern)
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
- `include`: explicit list — `data/**/*.ts`, `interfaces/**/*.ts`, `llm/**/*.ts`, `services/**/*.ts`, `shared/**/*.ts`, `integrations/**/*.ts` (excludes `tests/` from the production build; tests use a separate config or Vitest's own resolution)

---

## Prisma Schema

Full schema covering all entities named in the spec. pgvector extension enabled. Embedding tables present but unpopulated — vector ops are a later-step concern. Generator uses `prisma-client` with output `../generated/prisma`.

### Generator & Datasource

```prisma
generator client {
  provider        = "prisma-client"
  output          = "../generated/prisma"
  previewFeatures = ["postgresqlExtensions"]
}

datasource db {
  provider   = "postgresql"
  extensions = [vector]
}
```

### Enums

```prisma
enum TaskStatus {
  TODO
  IN_PROGRESS
  DONE
  BLOCKED
}

enum TaskType {
  CODING
  DEBUGGING
  INVESTIGATION
  ADR
  TEST_GENERATION
  MEETING_REVIEW
}

enum TaskPriority {
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

enum NoteType {
  dump
  investigation
  review
  docs
  guide
  learning
  decision
}

enum NoteParent {
  MEETING
  TASK
  SESSION
  REPO
}

enum RepoProvider {
  GITHUB
  GITLAB
  BITBUCKET
}
```

### Models

```prisma
model User {
  id        Int       @id @default(autoincrement())
  email     String    @unique
  createdAt DateTime  @default(now())
  tasks     Task[]
  sessions  Session[]
  notes     Note[]
}

model Repo {
  id                  Int                  @id @default(autoincrement())
  name                String
  url                 String               @unique
  platform            RepoProvider         @default(GITHUB)
  createdAt           DateTime             @default(now())
  updatedAt           DateTime             @updatedAt
  tasks               Task[]
  meetings            Meeting[]
  notes               Note[]
  codeChunkEmbeddings CodeChunkEmbedding[]
}

model Meeting {
  id                  Int                  @id @default(autoincrement())
  title               String
  outline             String?
  keyPoints           String[]
  krispUrl            String?
  notionUrl           String?
  repoId              Int?
  repo                Repo?                @relation(fields: [repoId], references: [id], onDelete: SetNull)
  tasks               Task[]
  actionItems         ActionItem[]
  sessions            Session[]
  notes               Note[]
  embedding           MeetingEmbedding?
  calibrationExamples CalibrationExample[]
  createdAt           DateTime             @default(now())
  updatedAt           DateTime             @updatedAt

  @@index([repoId])
}

model ActionItem {
  id        Int       @id @default(autoincrement())
  action    String
  dueDate   DateTime?
  meetingId Int
  meeting   Meeting   @relation(fields: [meetingId], references: [id], onDelete: Cascade)
  taskId    Int?
  task      Task?     @relation(fields: [taskId], references: [id], onDelete: SetNull)
  createdAt DateTime  @default(now())

  @@index([meetingId])
  @@index([taskId])
}

model Task {
  id                  Int                  @id @default(autoincrement())
  title               String
  description         String?
  status              TaskStatus           @default(TODO)
  priority            TaskPriority?
  dueDate             DateTime?
  taskType            TaskType
  externalTaskId      String?
  branch              String?
  repoId              Int?
  repo                Repo?                @relation(fields: [repoId], references: [id], onDelete: SetNull)
  meetingId           Int?
  meeting             Meeting?             @relation(fields: [meetingId], references: [id], onDelete: SetNull)
  createdById         Int?
  createdBy           User?                @relation(fields: [createdById], references: [id], onDelete: SetNull)
  sessions            SessionTask[]
  actionItems         ActionItem[]
  notes               Note[]
  embedding           TaskEmbedding?
  workflowRuns        WorkflowRun[]
  calibrationExamples CalibrationExample[]
  createdAt           DateTime             @default(now())
  updatedAt           DateTime             @updatedAt

  @@index([repoId])
  @@index([meetingId])
  @@index([createdById])
}

model Session {
  id            Int           @id @default(autoincrement())
  status        SessionStatus @default(ACTIVE)
  workflowState Json?
  meetingId     Int?
  meeting       Meeting?      @relation(fields: [meetingId], references: [id], onDelete: SetNull)
  createdById   Int?
  createdBy     User?         @relation(fields: [createdById], references: [id], onDelete: SetNull)
  startedAt     DateTime      @default(now())
  endedAt       DateTime?
  tasks         SessionTask[]
  workflowRuns  WorkflowRun[]
  notes         Note[]
  createdAt     DateTime      @default(now())
  updatedAt     DateTime      @updatedAt

  @@index([meetingId])
  @@index([createdById])
}

model SessionTask {
  sessionId Int
  taskId    Int
  session   Session @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  task      Task    @relation(fields: [taskId], references: [id], onDelete: Cascade)

  @@id([sessionId, taskId])
}

model Note {
  id          Int            @id @default(autoincrement())
  title       String
  content     String
  type        NoteType
  parentType  NoteParent
  meetingId   Int?
  meeting     Meeting?       @relation(fields: [meetingId], references: [id], onDelete: Cascade)
  taskId      Int?
  task        Task?          @relation(fields: [taskId], references: [id], onDelete: Cascade)
  sessionId   Int?
  session     Session?       @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  repoId      Int?
  repo        Repo?          @relation(fields: [repoId], references: [id], onDelete: Cascade)
  createdById Int?
  createdBy   User?          @relation(fields: [createdById], references: [id], onDelete: SetNull)
  embedding   NoteEmbedding?
  createdAt   DateTime       @default(now())

  @@index([parentType])
  @@index([meetingId])
  @@index([taskId])
  @@index([sessionId])
  @@index([repoId])
  @@index([createdById])
}

model IntegrationConfig {
  id        Int      @id @default(autoincrement())
  source    String   @unique
  token     String   // ciphertext only — encryption/decryption in repository layer
  metadata  Json?
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model WorkflowRun {
  id          Int            @id @default(autoincrement())
  workflowId  String
  sessionId   Int?
  session     Session?       @relation(fields: [sessionId], references: [id], onDelete: SetNull)
  taskId      Int?
  task        Task?          @relation(fields: [taskId], references: [id], onDelete: SetNull)
  status      WorkflowStatus @default(PENDING)
  input       Json?
  output      Json?
  startedAt   DateTime       @default(now())
  completedAt DateTime?
  createdAt   DateTime       @default(now())
  updatedAt   DateTime       @updatedAt

  @@index([workflowId])
  @@index([sessionId])
  @@index([taskId])
}

model CalibrationExample {
  id         Int      @id @default(autoincrement())
  taskId     Int?
  task       Task?    @relation(fields: [taskId], references: [id], onDelete: Cascade)
  meetingId  Int?
  meeting    Meeting? @relation(fields: [meetingId], references: [id], onDelete: Cascade)
  label      Boolean
  similarity Float?
  createdAt  DateTime @default(now())

  @@index([taskId])
  @@index([meetingId])
}

model SemanticConfig {
  id        Int      @id @default(autoincrement())
  key       String   @unique
  value     Float
  updatedAt DateTime @updatedAt
}

// Embedding tables — separate per entity, populated in later steps
model TaskEmbedding {
  id        Int                         @id @default(autoincrement())
  taskId    Int                         @unique
  task      Task                        @relation(fields: [taskId], references: [id], onDelete: Cascade)
  embedding Unsupported("vector(768)")?
  updatedAt DateTime                    @updatedAt
}

model MeetingEmbedding {
  id        Int                         @id @default(autoincrement())
  meetingId Int                         @unique
  meeting   Meeting                     @relation(fields: [meetingId], references: [id], onDelete: Cascade)
  embedding Unsupported("vector(768)")?
  updatedAt DateTime                    @updatedAt
}

model NoteEmbedding {
  id        Int                         @id @default(autoincrement())
  noteId    Int                         @unique
  note      Note                        @relation(fields: [noteId], references: [id], onDelete: Cascade)
  embedding Unsupported("vector(768)")?
  updatedAt DateTime                    @updatedAt
}

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

**pgvector setup**: The first migration includes `CREATE EXTENSION IF NOT EXISTS vector;` as a raw SQL statement. All vector queries use Prisma's `$queryRaw` — no ORM abstraction over vector operations.

---

## MCP Interface

One tool registered in Step 1: **`get_task_context`**.

```
Input:  { task_id: number }
Output: TaskContext (see shared/types.ts)
```

**Call chain**:

```
interfaces/mcp/index.ts
  → data/repositories/task.ts :: getTaskContext(taskId)
  → Prisma Client
  → Postgres
```

`getTaskContext` returns a `TaskContext` — the typed contract between the data layer and the LLM layer. It includes the full task with its linked meeting (if any), meeting action items, external task ID, branch, repo relation, and status.

### shared/types.ts — TaskContext

```typescript
// Re-export Prisma enums — single source of truth, stays in sync with schema
export { TaskStatus, TaskPriority, TaskType, RepoProvider } from '../generated/prisma'

export type TaskContext = {
  id: number
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority | null
  dueDate: Date | null
  taskType: TaskType
  externalTaskId: string | null
  branch: string | null
  repo: {
    id: number
    name: string
    url: string
    platform: RepoProvider
  } | null
  meeting: {
    id: number
    title: string
    outline: string | null
    keyPoints: string[]
    krispUrl: string | null
    actionItems: {
      id: number
      action: string
      dueDate: Date | null
    }[]
  } | null
}
```

`TaskContext` is the canonical type for what the LLM layer receives. Enums are re-exported from the generated Prisma client — never re-declared. This keeps `shared/types.ts` in sync with the schema automatically. It is imported by both `data/repositories/` (to type the return) and `mcp/` (to type the tool response). Any schema change that affects what the LLM layer sees must change `TaskContext` first.

---

## Skill Template

`llm/prompts/task_start.md` — plain text with `{{variable}}` placeholders. No templating engine. Services layer (Step 2) does a direct string substitution pass. Unresolved placeholders are a hard error, not silent pass-through.

```
Task: {{title}} ({{task_id}})
Type: {{task_type}} | Status: {{status}}
External ID: {{external_task_id}}
Branch: {{branch}}
Repo: {{repo_name}}
Due: {{due_date}}

Context:
{{context}}
```

**Variables for `task_start`**:

| Variable | Source | Type |
|---|---|---|
| `{{task_id}}` | TaskContext.id | number |
| `{{title}}` | TaskContext.title | string |
| `{{task_type}}` | TaskContext.taskType | TaskType enum |
| `{{status}}` | TaskContext.status | TaskStatus enum |
| `{{external_task_id}}` | TaskContext.externalTaskId | string \| null |
| `{{branch}}` | TaskContext.branch | string \| null |
| `{{repo_name}}` | TaskContext.repo.name | string \| null |
| `{{due_date}}` | TaskContext.dueDate | Date \| null |
| `{{context}}` | Serialised TaskContext | JSON string |

Unit test: given a valid `TaskContext`, every `{{variable}}` in the template is replaced. Any unresolved placeholder in the output causes the test to fail.

---

## Contract Test

**File**: `tests/contracts/data-to-mcp.test.ts`
**Runner**: Vitest
**Requires**: Postgres running (docker-compose)

```
1. Seed: insert a Repo, Meeting with ActionItems, and Task (with repo + meeting FKs) to Postgres via Prisma
2. Call: getTaskContext(task.id) directly
3. Assert: every field in the returned TaskContext matches the seed
         — correct types, no missing fields, no extra fields
         — id is a number (autoincrement), not a string
         — repo is non-null with matching id, name, url, platform
         — meeting is non-null with matching fields
         — meeting.actionItems is an array with matching id, action, dueDate
         — externalTaskId is null when not set (not undefined, not "")
         — branch is null when not set
4. Teardown: delete seeded records (in reverse FK order)
```

The test does not go through the MCP wire protocol — it calls the repository function directly. The MCP tool is a thin wrapper; the contract is at the repository layer.

**What "type-checked and complete" means in practice**:

- `id` is a number (int autoincrement)
- `title` is a string matching the seeded string exactly
- `dueDate` is a `Date` object (not a string)
- `meeting` is non-null and its fields match the seeded meeting
- `meeting.actionItems` is an array of objects with `id`, `action`, `dueDate`
- `repo` is non-null with `id`, `name`, `url`, `platform` matching the seeded repo
- `externalTaskId` is `null` when not set (not `undefined`, not `""`)
- `branch` is `null` when not set (not `undefined`, not `""`)

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
- Adds `docker-compose.yaml`, `data/`, `mcp/`, `llm/`, `services/`, `shared/`, `integrations/`, `tests/`
- Adds Prisma to `package.json`

**What could break**:

- The existing `bin` entry in `package.json` points to `./build/index.js` — this still holds after migration since `interfaces/mcp/index.ts` compiles to `build/interfaces/mcp/index.js`. The `bin` path needs updating to `./build/interfaces/mcp/index.js`.
- `.claude-plugin/plugin.json` has no path dependency — unaffected.

**Irreversible decisions in this step**:

- Committing to Prisma as the query layer. Migration away later would require rewriting `data/repositories/` and all migrations.
- Top-level directory structure. Changing this post-Step 2 would require services refactoring.

---

## Verification

Step 1 is complete when:

1. `docker-compose up -d` starts Postgres with pgvector
2. `prisma migrate dev` applies the schema without error
3. `npx vitest run tests/contracts/data-to-mcp.test.ts` passes — seeded data returned type-checked and complete
4. `npx vitest run tests/unit/` passes — skill variable injection resolves all placeholders
5. `tsc --noEmit` passes with zero errors
