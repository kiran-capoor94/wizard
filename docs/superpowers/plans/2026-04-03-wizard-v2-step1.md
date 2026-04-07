# Wizard v2 Step 1 — Data → LLM Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish Postgres + pgvector as the data foundation and prove that the LLM layer receives exactly what Postgres contains — type-checked and complete.

**Architecture:** Delete `src/` and restructure into the spec's top-level layered directories (`data/`, `interfaces/`, `shared/`, `llm/`, `services/`, `integrations/`, `tests/`). Prisma owns the schema. The data layer owns repositories — typed query interfaces between Postgres and the services layer. One MCP tool (`get_task_context`) is registered. The step is proven by a contract test that seeds data, queries it via the repository, and asserts field-for-field correctness.

**Tech Stack:** TypeScript (ESM, bundler), Yarn 4 (node-modules linker), Prisma (`prisma-client` generator with output to `generated/prisma`), pgvector via `pgvector/pgvector:pg16` Docker image, Vitest.

---

## File Map

| Action | Path                                  | Responsibility                                                   |
| ------ | ------------------------------------- | ---------------------------------------------------------------- |
| Create | `.yarnrc.yml`                         | Switch Yarn to node-modules linker (Prisma PnP incompatibility)  |
| Create | `docker-compose.yaml`                 | Postgres + pgvector local container                              |
| Create | `.env`                                | `DATABASE_URL` (gitignored)                                      |
| Create | `vitest.config.ts`                    | Test runner config                                               |
| Create | `prisma/schema.prisma`                | Full Prisma schema — all entities from spec                      |
| Create | `data/repositories/task.ts`           | `getTaskContext(taskId)` — the typed repository function         |
| Create | `interfaces/mcp/index.ts`             | MCP server with `health` + `get_task_context` tools              |
| Create | `shared/types.ts`                     | `TaskContext` type + re-exported Prisma enums                    |
| Create | `llm/prompts/task_start.md`           | First skill template with `{{variable}}` placeholders            |
| Create | `integrations/notion/index.ts`        | Moved from `src/notion/index.ts` (bug fix included)              |
| Create | `tests/contracts/data-to-mcp.test.ts` | Contract test — Step 1 proof criteria                            |
| Create | `tests/unit/skill-injection.test.ts`  | Unit test — skill variable injection                             |
| Modify | `package.json`                        | Add deps, update `bin`, update `build` script, add `test` script |
| Modify | `tsconfig.json`                       | `rootDir: .`, `include` explicit list, exclude tests             |
| Modify | `.gitignore`                          | Add `.env`, `build/`, `generated/`                               |
| Delete | `src/index.ts`                        | Replaced by `interfaces/mcp/index.ts`                            |
| Delete | `src/middleware.ts`                   | Empty stub                                                       |
| Delete | `src/tools/attention-list.ts`         | Empty stub                                                       |
| Delete | `src/notion/index.ts`                 | Moved to `integrations/notion/index.ts`                          |

---

## Task 1: Bootstrap — Yarn, Docker, Dependencies

**Files:**

- Create: `.yarnrc.yml`
- Create: `docker-compose.yaml`
- Create: `.env`
- Modify: `package.json`
- Modify: `.gitignore`

---

- [ ] **Step 1.1: Create `.yarnrc.yml` — switch to node-modules linker**

Prisma is incompatible with Yarn PnP. This must be set before installing any packages.

```yaml
# .yarnrc.yml
nodeLinker: node-modules
```

- [ ] **Step 1.2: Create `docker-compose.yaml`**

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

- [ ] **Step 1.3: Create `.env`**

```
DATABASE_URL="postgresql://wizard:wizard@localhost:5432/wizard"
```

- [ ] **Step 1.4: Add `.env`, `build/`, and `generated/` to `.gitignore`**

Append to `.gitignore`:

```
.env
build/
generated/
```

- [ ] **Step 1.5: Update `package.json`**

Replace the full content of `package.json` with:

```json
{
  "name": "wizard",
  "packageManager": "yarn@4.12.0",
  "type": "module",
  "bin": "./build/interfaces/mcp/index.js",
  "prisma": {
    "schema": "prisma/schema.prisma"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.28.0",
    "@notionhq/client": "^5.15.0",
    "@prisma/client": "^6.0.0",
    "zod": "^4.3.6"
  },
  "devDependencies": {
    "@types/node": "^25.5.0",
    "pgvector": "^0.2.0",
    "prisma": "^6.0.0",
    "typescript": "^6.0.2",
    "vitest": "^3.0.0"
  },
  "scripts": {
    "build": "tsc && chmod 755 build/interfaces/mcp/index.js",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "files": ["build"]
}
```

- [ ] **Step 1.6: Install dependencies**

```bash
yarn install
```

Expected: packages install into `node_modules/` (not PnP). You should see `node_modules/prisma/` and `node_modules/@prisma/` appear.

- [ ] **Step 1.7: Start Postgres**

```bash
docker-compose up -d
```

Expected output ends with:

```
✔ Container wizard-postgres-1  Started
```

- [ ] **Step 1.8: Verify Postgres is accepting connections**

```bash
docker-compose exec postgres psql -U wizard -d wizard -c "SELECT 1;"
```

Expected:

```
 ?column?
----------
        1
```

- [ ] **Step 1.9: Create `.env.example`**

`.env` is gitignored (real credentials). `.env.example` documents the required variables with placeholder values and is committed.

```
DATABASE_URL="postgresql://wizard:wizard@localhost:5432/wizard"
```

Save this as `.env.example` at the project root.

- [ ] **Step 1.10: Commit**

```bash
git add .yarnrc.yml docker-compose.yaml .env.example package.json .gitignore
git commit -m "chore: bootstrap yarn node-modules, docker, and dependencies"
```

---

## Task 2: Restructure — Migrate `src/`, Update `tsconfig.json`

**Files:**

- Create: `interfaces/mcp/index.ts`
- Create: `integrations/notion/index.ts`
- Create: `vitest.config.ts`
- Modify: `tsconfig.json`
- Delete: `src/index.ts`, `src/middleware.ts`, `src/tools/attention-list.ts`, `src/notion/index.ts`

---

- [ ] **Step 2.1: Create directory skeleton**

```bash
mkdir -p data/repositories interfaces/mcp interfaces/cli interfaces/plugin shared llm/prompts llm/adapters llm/schemas llm/packaging services integrations/notion tests/contracts tests/unit
```

- [ ] **Step 2.2: Create `interfaces/mcp/index.ts`**

This migrates `src/index.ts`. The `health` tool response is fixed (`text` field was missing), the server is connected to a transport, and `registerTool` is replaced with the current `tool` API.

```typescript
// interfaces/mcp/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({
  name: "wizard",
  version: "0.2.0",
});

server.tool("health", "Get health of Wizard System", {}, async () => ({
  content: [{ type: "text", text: "OK" }],
}));

const transport = new StdioServerTransport();
await server.connect(transport);
```

- [ ] **Step 2.3: Create `integrations/notion/index.ts`**

Move from `src/notion/index.ts`. Fix the bug: `(database_id = dBId)` → `({ database_id: dBId })`.

```typescript
// integrations/notion/index.ts
import { Client } from "@notionhq/client";

export function createNotionClient(): Client {
  const auth = process.env.NOTION_API_KEY;
  if (!auth) throw new Error("NOTION_API_KEY is not set");
  return new Client({ auth });
}

export function getNotionDBByID(dBId: string) {
  const client = createNotionClient();
  return client.databases.retrieve({ database_id: dBId });
}
```

- [ ] **Step 2.4: Create `vitest.config.ts`**

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
  },
});
```

- [ ] **Step 2.5: Update `tsconfig.json`**

Replace the full content with:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "Node16",
    "moduleResolution": "bundler",
    "outDir": "./build",
    "rootDir": ".",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": [
    "data/**/*.ts",
    "interfaces/**/*.ts",
    "shared/**/*.ts",
    "llm/**/*.ts",
    "services/**/*.ts",
    "integrations/**/*.ts"
  ],
  "exclude": ["node_modules", "build", "generated", "tests"]
}
```

- [ ] **Step 2.6: Delete `src/`**

```bash
rm -rf src/
```

- [ ] **Step 2.7: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors. If you see errors about missing Prisma types, that's expected until Task 3 — proceed anyway and re-run after migration.

- [ ] **Step 2.8: Commit**

```bash
git add interfaces/mcp/index.ts integrations/notion/index.ts vitest.config.ts tsconfig.json
git rm -r src/
git commit -m "refactor: migrate src/ to layered directory structure"
```

---

## Task 3: Prisma Schema + Migration

**Files:**

- Create: `prisma/schema.prisma`
- Create: `prisma/migrations/` (generated by Prisma)

---

- [ ] **Step 3.1: Create `prisma/schema.prisma`**

The schema uses `prisma-client` generator with output to `../generated/prisma`. All IDs are `Int @id @default(autoincrement())`. The full schema includes all models from the spec: User, Repo, Meeting, ActionItem, Task, Session, SessionTask, Note, IntegrationConfig, WorkflowRun, CalibrationExample, SemanticConfig, and all embedding tables.

```prisma
// prisma/schema.prisma

generator client {
  provider        = "prisma-client"
  output          = "../generated/prisma"
  previewFeatures = ["postgresqlExtensions"]
}

datasource db {
  provider   = "postgresql"
  extensions = [vector]
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

enum TaskType {
  CODING
  DEBUGGING
  INVESTIGATION
  ADR
  TEST_GENERATION
  MEETING_REVIEW
}

enum TaskStatus {
  TODO
  IN_PROGRESS
  DONE
  BLOCKED
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

enum RepoProvider {
  GITHUB
  GITLAB
  BITBUCKET
}

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
  token     String
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

- [ ] **Step 3.2: Verify the schema parses cleanly**

```bash
npx prisma validate
```

Expected: `The schema at prisma/schema.prisma is valid`

- [ ] **Step 3.3: Run the first migration**

```bash
npx prisma migrate dev --name init
```

Expected: Prisma creates `prisma/migrations/[timestamp]_init/migration.sql`, applies it to the database, and runs `prisma generate`. The generated client is output to `generated/prisma/`.

If you see an error about the `vector` extension not found, confirm the Docker image is `pgvector/pgvector:pg16` (not plain `postgres`).

- [ ] **Step 3.4: Verify the schema applied**

```bash
docker-compose exec postgres psql -U wizard -d wizard -c "\dt"
```

Expected: table list including `User`, `Repo`, `Meeting`, `ActionItem`, `Task`, `Session`, `SessionTask`, `Note`, `IntegrationConfig`, `WorkflowRun`, `CalibrationExample`, `SemanticConfig`, `TaskEmbedding`, `MeetingEmbedding`, `NoteEmbedding`, `CodeChunkEmbedding`.

- [ ] **Step 3.5: Verify TypeScript now compiles cleanly**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3.6: Commit**

```bash
git add prisma/schema.prisma prisma/migrations/ package.json
git commit -m "feat: add full prisma schema with pgvector"
```

---

## Task 4: `shared/types.ts`

**Files:**

- Create: `shared/types.ts`

---

- [ ] **Step 4.1: Create `shared/types.ts`**

`TaskContext` is the canonical type for what the LLM layer receives. Enums are re-exported from the generated Prisma client — never re-declared here. This means the TypeScript types are always in sync with the schema.

Note: The generated client lives at `../generated/prisma` (relative to the prisma schema). Import paths reference this location.

```typescript
// shared/types.ts
export {
  TaskStatus,
  TaskPriority,
  TaskType,
  SessionStatus,
  WorkflowStatus,
  RepoProvider,
  NoteType,
  NoteParent,
} from "../generated/prisma/index.js";
import type {
  TaskStatus,
  TaskPriority,
  TaskType,
  RepoProvider,
} from "../generated/prisma/index.js";

export type TaskContext = {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority | null;
  dueDate: Date | null;
  taskType: TaskType;
  externalTaskId: string | null;
  branch: string | null;
  repo: {
    id: number;
    name: string;
    url: string;
    platform: RepoProvider;
  } | null;
  meeting: {
    id: number;
    title: string;
    outline: string | null;
    keyPoints: string[];
    krispUrl: string | null;
    actionItems: {
      id: number;
      action: string;
      dueDate: Date | null;
    }[];
  } | null;
};
```

- [ ] **Step 4.2: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4.3: Commit**

```bash
git add shared/types.ts
git commit -m "feat: add TaskContext type to shared/types"
```

---

## Task 5: Write the Failing Contract Test

**Files:**

- Create: `tests/contracts/data-to-mcp.test.ts`

The contract test is the Step 1 proof. Write it before implementing the repository function — it must fail first.

---

- [ ] **Step 5.1: Create `tests/contracts/data-to-mcp.test.ts`**

Key differences from the old schema: IDs are `number` (autoincrement), `ActionItem` is a separate model (not `String[]`), `externalTaskId` replaces `jiraKey`, `branch` replaces `githubBranch`, `repo` is a FK relation replacing `githubRepo`, and `TaskPriority` replaces `Priority`.

```typescript
// tests/contracts/data-to-mcp.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { PrismaClient } from "../../generated/prisma/index.js";
import { getTaskContext } from "../../data/repositories/task.js";

const prisma = new PrismaClient();

describe("Data → LLM Layer contract", () => {
  let repoId: number;
  let meetingId: number;
  let taskId: number;
  let actionItemId: number;

  beforeAll(async () => {
    const repo = await prisma.repo.create({
      data: {
        name: "sisu-universe",
        url: "https://github.com/sisu-health/sisu-universe",
        platform: "GITHUB",
      },
    });
    repoId = repo.id;

    const meeting = await prisma.meeting.create({
      data: {
        title: "Sprint Planning",
        outline: "Plan the sprint",
        keyPoints: ["Deploy auth", "Fix bug"],
        krispUrl: "https://krisp.ai/meetings/test",
      },
    });
    meetingId = meeting.id;

    const actionItem = await prisma.actionItem.create({
      data: {
        action: "Create ticket PD-42",
        dueDate: new Date("2026-04-12T00:00:00.000Z"),
        meetingId: meeting.id,
      },
    });
    actionItemId = actionItem.id;

    const task = await prisma.task.create({
      data: {
        title: "Add authentication",
        description: "Implement JWT auth",
        status: "IN_PROGRESS",
        priority: "HIGH",
        dueDate: new Date("2026-04-10T00:00:00.000Z"),
        taskType: "CODING",
        externalTaskId: "PD-42",
        branch: "feat/auth",
        repoId: repo.id,
        meetingId: meeting.id,
      },
    });
    taskId = task.id;
  });

  afterAll(async () => {
    await prisma.task.delete({ where: { id: taskId } });
    await prisma.actionItem.delete({ where: { id: actionItemId } });
    await prisma.meeting.delete({ where: { id: meetingId } });
    await prisma.repo.delete({ where: { id: repoId } });
    await prisma.$disconnect();
  });

  it("returns a TaskContext matching the seeded task exactly", async () => {
    const context = await getTaskContext(taskId);

    expect(context).not.toBeNull();
    expect(context!.id).toBe(taskId);
    expect(context!.title).toBe("Add authentication");
    expect(context!.description).toBe("Implement JWT auth");
    expect(context!.status).toBe("IN_PROGRESS");
    expect(context!.priority).toBe("HIGH");
    expect(context!.dueDate).toBeInstanceOf(Date);
    expect(context!.dueDate!.toISOString()).toBe("2026-04-10T00:00:00.000Z");
    expect(context!.taskType).toBe("CODING");
    expect(context!.externalTaskId).toBe("PD-42");
    expect(context!.branch).toBe("feat/auth");
  });

  it("returns the linked repo with all fields matching the seed", async () => {
    const context = await getTaskContext(taskId);
    const repo = context!.repo;

    expect(repo).not.toBeNull();
    expect(repo!.id).toBe(repoId);
    expect(repo!.name).toBe("sisu-universe");
    expect(repo!.url).toBe("https://github.com/sisu-health/sisu-universe");
    expect(repo!.platform).toBe("GITHUB");
  });

  it("returns null for externalTaskId when not set", async () => {
    const bare = await prisma.task.create({
      data: { title: "Bare task", status: "TODO", taskType: "INVESTIGATION" },
    });

    const context = await getTaskContext(bare.id);

    expect(context!.externalTaskId).toBeNull();
    expect(context!.externalTaskId).not.toBeUndefined();
    expect(context!.externalTaskId).not.toBe("");

    await prisma.task.delete({ where: { id: bare.id } });
  });

  it("returns the linked meeting with action items matching the seed", async () => {
    const context = await getTaskContext(taskId);
    const meeting = context!.meeting;

    expect(meeting).not.toBeNull();
    expect(meeting!.id).toBe(meetingId);
    expect(meeting!.title).toBe("Sprint Planning");
    expect(meeting!.outline).toBe("Plan the sprint");
    expect(meeting!.keyPoints).toEqual(["Deploy auth", "Fix bug"]);
    expect(meeting!.krispUrl).toBe("https://krisp.ai/meetings/test");

    expect(meeting!.actionItems).toHaveLength(1);
    expect(meeting!.actionItems[0].id).toBe(actionItemId);
    expect(meeting!.actionItems[0].action).toBe("Create ticket PD-42");
    expect(meeting!.actionItems[0].dueDate).toBeInstanceOf(Date);
    expect(meeting!.actionItems[0].dueDate!.toISOString()).toBe(
      "2026-04-12T00:00:00.000Z",
    );
  });

  it("returns null for meeting when task has none", async () => {
    const bare = await prisma.task.create({
      data: {
        title: "No meeting task",
        status: "TODO",
        taskType: "INVESTIGATION",
      },
    });

    const context = await getTaskContext(bare.id);

    expect(context!.meeting).toBeNull();

    await prisma.task.delete({ where: { id: bare.id } });
  });

  it("returns null for repo when task has none", async () => {
    const bare = await prisma.task.create({
      data: {
        title: "No repo task",
        status: "TODO",
        taskType: "INVESTIGATION",
      },
    });

    const context = await getTaskContext(bare.id);

    expect(context!.repo).toBeNull();

    await prisma.task.delete({ where: { id: bare.id } });
  });

  it("returns null when task does not exist", async () => {
    const context = await getTaskContext(999999);
    expect(context).toBeNull();
  });
});
```

- [ ] **Step 5.2: Run the test — verify it fails with the right error**

```bash
yarn test tests/contracts/data-to-mcp.test.ts
```

Expected failure:

```
Error: Failed to resolve import "../../data/repositories/task.js"
```

This is the correct failure — the module doesn't exist yet. If you see a Postgres connection error instead, verify `docker-compose up -d` is running and `DATABASE_URL` in `.env` is correct.

- [ ] **Step 5.3: Commit the failing test**

```bash
git add tests/contracts/data-to-mcp.test.ts
git commit -m "test(contract): add data-to-mcp contract test (failing)"
```

---

## Task 6: `data/repositories/task.ts` — Make the Contract Test Pass

**Files:**

- Create: `data/repositories/task.ts`

The data layer owns repositories. A repository is the typed query interface between Postgres and the services layer. Services call repositories, never Postgres directly.

---

- [ ] **Step 6.1: Create `data/repositories/task.ts`**

```typescript
// data/repositories/task.ts
import { PrismaClient } from "../../generated/prisma/index.js";
import type { TaskContext } from "../../shared/types.js";

const prisma = new PrismaClient();

export async function getTaskContext(
  taskId: number,
): Promise<TaskContext | null> {
  return prisma.task.findUnique({
    where: { id: taskId },
    select: {
      id: true,
      title: true,
      description: true,
      status: true,
      priority: true,
      dueDate: true,
      taskType: true,
      externalTaskId: true,
      branch: true,
      repo: {
        select: {
          id: true,
          name: true,
          url: true,
          platform: true,
        },
      },
      meeting: {
        select: {
          id: true,
          title: true,
          outline: true,
          keyPoints: true,
          krispUrl: true,
          actionItems: {
            select: {
              id: true,
              action: true,
              dueDate: true,
            },
          },
        },
      },
    },
  });
}
```

- [ ] **Step 6.2: Run the contract test — verify it passes**

```bash
yarn test tests/contracts/data-to-mcp.test.ts
```

Expected:

```
✓ Data → LLM Layer contract > returns a TaskContext matching the seeded task exactly
✓ Data → LLM Layer contract > returns the linked repo with all fields matching the seed
✓ Data → LLM Layer contract > returns null for externalTaskId when not set
✓ Data → LLM Layer contract > returns the linked meeting with action items matching the seed
✓ Data → LLM Layer contract > returns null for meeting when task has none
✓ Data → LLM Layer contract > returns null for repo when task has none
✓ Data → LLM Layer contract > returns null when task does not exist

Test Files  1 passed (1)
Tests       7 passed (7)
```

- [ ] **Step 6.3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 6.4: Commit**

```bash
git add data/repositories/task.ts
git commit -m "feat: add getTaskContext repository — contract test passing"
```

---

## Task 7: Register `get_task_context` in the MCP Server

**Files:**

- Modify: `interfaces/mcp/index.ts`

---

- [ ] **Step 7.1: Update `interfaces/mcp/index.ts` to register `get_task_context`**

Replace the full file content:

```typescript
// interfaces/mcp/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getTaskContext } from "../data/repositories/task.js";

const server = new McpServer({
  name: "wizard",
  version: "0.2.0",
});

server.tool("health", "Get health of Wizard System", {}, async () => ({
  content: [{ type: "text", text: "OK" }],
}));

server.tool(
  "get_task_context",
  "Get the full context for a task by ID. Returns task details, linked meeting with action items, repo, external task ID, and branch.",
  { task_id: z.number().int().describe("The Wizard task ID (integer)") },
  async ({ task_id }) => {
    const context = await getTaskContext(task_id);

    if (!context) {
      return {
        content: [{ type: "text", text: `Task not found: ${task_id}` }],
        isError: true,
      };
    }

    return {
      content: [{ type: "text", text: JSON.stringify(context, null, 2) }],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

- [ ] **Step 7.2: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 7.3: Commit**

```bash
git add interfaces/mcp/index.ts
git commit -m "feat: register get_task_context MCP tool"
```

---

## Task 8: First Skill Template

**Files:**

- Create: `llm/prompts/task_start.md`

---

- [ ] **Step 8.1: Create `llm/prompts/task_start.md`**

Plain text with `{{variable}}` placeholders. No templating engine — Orchestration (Step 2) does direct string substitution. Every placeholder listed in the variable table below must appear in the template.

```markdown
You are working on the following task. Use the context provided to begin work.

Task: {{title}} ({{task_id}})
Type: {{task_type}} | Status: {{status}}
External ID: {{external_task_id}}
Branch: {{branch}}
Due: {{due_date}}

Context:
{{context}}
```

**Variable table** (used by the unit test in Task 9):

| Placeholder            | Source                       | Type                                |
| ---------------------- | ---------------------------- | ----------------------------------- |
| `{{task_id}}`          | `TaskContext.id`             | number as string                    |
| `{{title}}`            | `TaskContext.title`          | string                              |
| `{{task_type}}`        | `TaskContext.taskType`       | TaskType enum as string             |
| `{{status}}`           | `TaskContext.status`         | TaskStatus enum as string           |
| `{{external_task_id}}` | `TaskContext.externalTaskId` | string or "none" when null          |
| `{{branch}}`           | `TaskContext.branch`         | string or "none" when null          |
| `{{due_date}}`         | `TaskContext.dueDate`        | ISO date string or "none" when null |
| `{{context}}`          | Full `TaskContext`           | JSON string                         |

- [ ] **Step 8.2: Commit**

```bash
git add llm/prompts/task_start.md
git commit -m "feat: add task_start skill template"
```

---

## Task 9: Unit Test — Skill Variable Injection

**Files:**

- Create: `tests/unit/skill-injection.test.ts`

This test does two things: verifies the `task_start.md` template has the expected placeholders, and verifies that a correct substitution leaves no unresolved `{{...}}` patterns.

The `injectVariables` function is inlined here — it belongs to the Orchestration layer (Step 2). The inline version is the spec, not the implementation.

---

- [ ] **Step 9.1: Create `tests/unit/skill-injection.test.ts`**

```typescript
// tests/unit/skill-injection.test.ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Inline implementation — the real version lives in services/ (Step 2).
// This function defines the expected contract for variable injection.
function injectVariables(
  template: string,
  variables: Record<string, string>,
): string {
  let result = template;
  for (const [key, value] of Object.entries(variables)) {
    result = result.replaceAll(`{{${key}}}`, value);
  }
  const unresolved = result.match(/\{\{[^}]+\}\}/g);
  if (unresolved) {
    throw new Error(`Unresolved placeholders: ${unresolved.join(", ")}`);
  }
  return result;
}

const TASK_START_PATH = join(process.cwd(), "llm/prompts/task_start.md");

const TASK_START_VARIABLES: Record<string, string> = {
  task_id: "42",
  title: "Add authentication",
  task_type: "CODING",
  status: "IN_PROGRESS",
  external_task_id: "PD-42",
  branch: "feat/auth",
  due_date: "2026-04-10T00:00:00.000Z",
  context: JSON.stringify({ id: 42, title: "Add authentication" }),
};

describe("task_start skill variable injection", () => {
  it("resolves all placeholders when given a complete variable map", () => {
    const template = readFileSync(TASK_START_PATH, "utf-8");
    const result = injectVariables(template, TASK_START_VARIABLES);

    expect(result).not.toMatch(/\{\{[^}]+\}\}/);
    expect(result).toContain("42");
    expect(result).toContain("Add authentication");
    expect(result).toContain("CODING");
    expect(result).toContain("IN_PROGRESS");
    expect(result).toContain("PD-42");
    expect(result).toContain("feat/auth");
  });

  it("contains exactly the expected placeholders and no others", () => {
    const template = readFileSync(TASK_START_PATH, "utf-8");
    const found = [...template.matchAll(/\{\{([^}]+)\}\}/g)].map((m) => m[1]);
    const expected = Object.keys(TASK_START_VARIABLES);

    expect(found.sort()).toEqual(expected.sort());
  });

  it("throws when a placeholder is not in the variable map", () => {
    const template = "Hello {{name}}";
    expect(() => injectVariables(template, {})).toThrow(
      "Unresolved placeholders: {{name}}",
    );
  });

  it("throws when variables are missing from a partial map", () => {
    const template = readFileSync(TASK_START_PATH, "utf-8");
    const partial = { task_id: "42", title: "Add authentication" };

    expect(() => injectVariables(template, partial)).toThrow(
      "Unresolved placeholders",
    );
  });
});
```

- [ ] **Step 9.2: Run the unit test**

```bash
yarn test tests/unit/skill-injection.test.ts
```

Expected:

```
✓ task_start skill variable injection > resolves all placeholders when given a complete variable map
✓ task_start skill variable injection > contains exactly the expected placeholders and no others
✓ task_start skill variable injection > throws when a placeholder is not in the variable map
✓ task_start skill variable injection > throws when variables are missing from a partial map

Test Files  1 passed (1)
Tests       4 passed (4)
```

If the second test fails ("contains exactly the expected placeholders"), the template has a placeholder not in `TASK_START_VARIABLES` or vice versa. Check the diff between `found` and `expected` in the failure output and update the template or the variable map accordingly.

- [ ] **Step 9.3: Commit**

```bash
git add tests/unit/skill-injection.test.ts
git commit -m "test(unit): add skill variable injection test"
```

---

## Task 10: Final Verification

---

- [ ] **Step 10.1: Run the full test suite**

```bash
yarn test
```

Expected:

```
Test Files  2 passed (2)
Tests       11 passed (11)
```

- [ ] **Step 10.2: TypeScript clean build**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 10.3: Verify Docker + Postgres are still healthy**

```bash
docker-compose exec postgres psql -U wizard -d wizard -c "SELECT count(*) FROM \"Task\";"
```

Expected:

```
 count
-------
     0
```

(Zero rows — test teardown cleaned up.)

- [ ] **Step 10.4: Step 1 is complete**

The proof criteria from the spec is met:

> Contract test asserting the LLM layer receives exactly what Postgres contains for a given query — type-checked and complete. Not just that something is returned.

`tests/contracts/data-to-mcp.test.ts` passes with seven assertions verifying: exact field values, correct `Date` type (not string) for `dueDate`, `null` (not `undefined` or `""`) for optional fields, linked meeting data with action items as a separate model, linked repo data, and null return for missing tasks.

- [ ] **Step 10.5: Final commit**

```bash
git add .
git commit -m "chore: step 1 complete — data-to-llm-layer contract passing"
```

---

## Troubleshooting

**Prisma: `Environment variable not found: DATABASE_URL`**
Ensure `.env` exists at the project root with `DATABASE_URL="postgresql://wizard:wizard@localhost:5432/wizard"`. Prisma reads `.env` automatically.

**Prisma: PnP-related resolution errors**
Confirm `.yarnrc.yml` contains `nodeLinker: node-modules` and that you ran `yarn install` after creating it. There should be a `node_modules/` directory at the project root.

**Prisma: Generated client not found**
The generator outputs to `generated/prisma/`. After running `npx prisma migrate dev` or `npx prisma generate`, verify `generated/prisma/index.js` exists. Import from `../../generated/prisma/index.js` (not `@prisma/client`).

**`pgvector` extension not found during migration**
The Docker image must be `pgvector/pgvector:pg16`, not plain `postgres:16`. Run `docker-compose down -v && docker-compose up -d` to recreate with the correct image.

**Contract test: Postgres connection refused**
Run `docker-compose up -d` and wait a few seconds for Postgres to be ready.

**`tsc --noEmit` errors on `Unsupported` type in schema**
This is a Prisma schema type, not TypeScript. TypeScript never sees `Unsupported(...)` — it's replaced by `null` in the generated client. This is expected and correct.

**Import errors with generated Prisma client**
The `prisma-client` generator (not `prisma-client-js`) outputs to `../generated/prisma` relative to the schema. All imports must use `../../generated/prisma/index.js` from `data/` or `shared/`, not `@prisma/client`.
