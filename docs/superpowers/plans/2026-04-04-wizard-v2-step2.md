# Wizard v2 Step 2 — Services Layer: Session Lifecycle & Workflow Execution

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the services layer — variable injection, pre-flight check, session lifecycle, and workflow execution as service functions — and prove that the LLM layer is invoked with prepared context, pre-flight passes before invocation, and session state survives a simulated crash.

**Architecture:** Each workflow is a service function. No separate orchestration layer. Pre-flight is a shared utility called at the start of every service function — not an interface concern. Services read context from Postgres, resolve skill template variables, run pre-flight (Postgres reachable + pgvector installed), and produce a formatted prompt for the LLM adapter. Session state is written to Postgres before any LLM invocation — making it crash-durable by design. Workflow definitions live in `core/workflows/`; services execute them, never define them. WorkflowRun audit trail is written inside service functions, before and after execution. Session has `meetingId` and `createdById` FKs for traceability. All IDs are `Int @id @default(autoincrement())`. The Prisma generator uses `"prisma-client"` with `output = "../generated/prisma"` — all imports from `../../generated/prisma/index.js`, not `@prisma/client`.

**Tech Stack:** TypeScript (ESM, bundler), Prisma (`prisma-client` generator, output `generated/prisma`), Vitest. No new dependencies beyond Step 1.

## File Map

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

---

## Task 1: `tsconfig.json` — Add `core/` Directory

**Files:**

- Modify: `tsconfig.json`

---

- [ ] **Step 1.1: Add `core` to `tsconfig.json` include**

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
    "integrations/**/*.ts",
    "services/**/*.ts",
    "core/**/*.ts"
  ],
  "exclude": ["node_modules", "build", "tests"]
}
```

- [ ] **Step 1.2: Create directory skeleton**

```bash
mkdir -p core/workflows
```

- [ ] **Step 1.3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 1.4: Commit**

```bash
git add tsconfig.json
git commit -m "chore: add core/ to tsconfig"
```

---

## Task 2: `services/inject.ts` — Variable Injection

**Files:**

- Create: `services/inject.ts`
- Create: `tests/unit/inject.test.ts`
- Modify: `tests/unit/skill-injection.test.ts` (update import)

The `injectVariables` function was inlined in the Step 1 unit test. It now moves to its permanent home in `services/`. The unit test is updated to import from there.

---

- [ ] **Step 2.1: Write the failing test**

```typescript
// tests/unit/inject.test.ts
import { describe, it, expect } from "vitest";
import { injectVariables } from "../../services/inject.js";

describe("injectVariables", () => {
  it("replaces all placeholders with their values", () => {
    const result = injectVariables("Hello {{name}}, your task is {{task}}", {
      name: "Kiran",
      task: "implement auth",
    });
    expect(result).toBe("Hello Kiran, your task is implement auth");
  });

  it("throws when a placeholder has no matching variable", () => {
    expect(() => injectVariables("Hello {{name}}", {})).toThrow(
      "Unresolved placeholders: {{name}}",
    );
  });

  it("throws listing all unresolved placeholders", () => {
    expect(() =>
      injectVariables("{{a}} and {{b}} and {{c}}", { a: "x" }),
    ).toThrow("Unresolved placeholders: {{b}}, {{c}}");
  });

  it("handles a template with no placeholders", () => {
    const result = injectVariables("No placeholders here.", {});
    expect(result).toBe("No placeholders here.");
  });

  it("replaces multiple occurrences of the same placeholder", () => {
    const result = injectVariables("{{x}} and {{x}}", { x: "hello" });
    expect(result).toBe("hello and hello");
  });
});
```

- [ ] **Step 2.2: Run the test — verify it fails**

```bash
yarn test tests/unit/inject.test.ts
```

Expected: `Error: Failed to resolve import "../../services/inject.js"`

- [ ] **Step 2.3: Create `services/inject.ts`**

```typescript
// services/inject.ts

export type Variables = Record<string, string>;

/**
 * Replaces {{key}} placeholders in a template with values from the variables map.
 * Throws if any placeholder remains unresolved after substitution.
 */
export function injectVariables(
  template: string,
  variables: Variables,
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
```

- [ ] **Step 2.4: Run the test — verify it passes**

```bash
yarn test tests/unit/inject.test.ts
```

Expected:

```
✓ injectVariables > replaces all placeholders with their values
✓ injectVariables > throws when a placeholder has no matching variable
✓ injectVariables > throws listing all unresolved placeholders
✓ injectVariables > handles a template with no placeholders
✓ injectVariables > replaces multiple occurrences of the same placeholder

Test Files  1 passed (1)
Tests       5 passed (5)
```

- [ ] **Step 2.5: Update `tests/unit/skill-injection.test.ts` to import from services**

Replace the inline `injectVariables` function at the top of the file with an import:

```typescript
// tests/unit/skill-injection.test.ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { injectVariables } from "../../services/inject.js";

// Remove the inline injectVariables function — it now lives in services/inject.ts

const TASK_START_PATH = join(process.cwd(), "llm/prompts/task_start.md");

const TASK_START_VARIABLES: Record<string, string> = {
  task_id: "42",
  title: "Add authentication",
  task_type: "CODING",
  status: "IN_PROGRESS",
  external_task_id: "PD-42",
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

- [ ] **Step 2.6: Run the full unit test suite**

```bash
yarn test tests/unit/
```

Expected: all tests pass (both `inject.test.ts` and `skill-injection.test.ts`).

- [ ] **Step 2.7: Commit**

```bash
git add services/inject.ts tests/unit/inject.test.ts tests/unit/skill-injection.test.ts
git commit -m "feat: add injectVariables to services/inject"
```

---

## Task 3: `services/preflight.ts` — Pre-Flight Check

**Files:**

- Create: `services/preflight.ts`
- Create: `tests/unit/preflight.test.ts`

---

- [ ] **Step 3.1: Write the failing test**

```typescript
// tests/unit/preflight.test.ts
import { describe, it, expect } from "vitest";
import { runPreflight } from "../../services/preflight.js";

describe("runPreflight", () => {
  it("returns ok: true when Postgres is reachable and pgvector is installed", async () => {
    // Requires: docker-compose up -d and DATABASE_URL set
    const result = await runPreflight();
    expect(result.ok).toBe(true);
  });
});
```

- [ ] **Step 3.2: Run the test — verify it fails**

```bash
yarn test tests/unit/preflight.test.ts
```

Expected: `Error: Failed to resolve import "../../services/preflight.js"`

- [ ] **Step 3.3: Create `services/preflight.ts`**

```typescript
// services/preflight.ts
import { PrismaClient } from "../../generated/prisma/index.js";

const prisma = new PrismaClient();

export type PreflightResult = { ok: true } | { ok: false; reason: string };

/**
 * Checks that Postgres is reachable and the pgvector extension is installed.
 * Must pass before any LLM invocation.
 */
export async function runPreflight(): Promise<PreflightResult> {
  try {
    await prisma.$queryRaw`SELECT 1`;
  } catch (err) {
    return { ok: false, reason: `Postgres unreachable: ${String(err)}` };
  }

  const rows = await prisma.$queryRaw<{ count: bigint }[]>`
    SELECT count(*) AS count
    FROM pg_extension
    WHERE extname = 'vector'
  `;
  if (Number(rows[0].count) === 0) {
    return { ok: false, reason: "pgvector extension not installed" };
  }

  return { ok: true };
}
```

- [ ] **Step 3.4: Run the test — verify it passes**

```bash
yarn test tests/unit/preflight.test.ts
```

Expected:

```
✓ runPreflight > returns ok: true when Postgres is reachable and pgvector is installed

Test Files  1 passed (1)
Tests       1 passed (1)
```

- [ ] **Step 3.5: Commit**

```bash
git add services/preflight.ts tests/unit/preflight.test.ts
git commit -m "feat: add runPreflight to services/preflight"
```

---

## Task 4: `services/session.ts` — Session Lifecycle

**Files:**

- Create: `services/session.ts`
- Create: `tests/unit/session.test.ts`

Session uses `Int @id @default(autoincrement())` IDs and has optional `meetingId` and `createdById` FK fields. All function signatures use `number` for IDs (sessionId: number, taskId: number).

---

- [ ] **Step 4.1: Write the failing test**

```typescript
// tests/unit/session.test.ts
import { describe, it, expect, afterEach } from "vitest";
import { PrismaClient } from "../../generated/prisma/index.js";
import {
  createSession,
  endSession,
  getSession,
  attachTaskToSession,
} from "../../services/session.js";

const prisma = new PrismaClient();
const createdSessionIds: number[] = [];
const createdTaskIds: number[] = [];

afterEach(async () => {
  // Clean up in FK order
  for (const id of createdSessionIds) {
    await prisma.sessionTask
      .deleteMany({ where: { sessionId: id } })
      .catch(() => {});
    await prisma.session.delete({ where: { id } }).catch(() => {});
  }
  for (const id of createdTaskIds) {
    await prisma.task.delete({ where: { id } }).catch(() => {});
  }
  createdSessionIds.length = 0;
  createdTaskIds.length = 0;
  await prisma.$disconnect();
});

describe("createSession", () => {
  it("creates an ACTIVE session and returns its int ID", async () => {
    const id = await createSession();
    createdSessionIds.push(id);

    expect(typeof id).toBe("number");

    // Re-query with a fresh client to prove it is in Postgres (not in-memory)
    const fresh = new PrismaClient();
    const session = await fresh.session.findUnique({ where: { id } });
    await fresh.$disconnect();

    expect(session).not.toBeNull();
    expect(session!.status).toBe("ACTIVE");
    expect(session!.startedAt).toBeInstanceOf(Date);
    expect(session!.endedAt).toBeNull();
  });

  it("creates a session with optional meetingId FK", async () => {
    const meeting = await prisma.meeting.create({
      data: { title: "Sprint planning", keyPoints: [] },
    });
    const id = await createSession({ meetingId: meeting.id });
    createdSessionIds.push(id);

    const session = await prisma.session.findUnique({ where: { id } });
    expect(session!.meetingId).toBe(meeting.id);

    await prisma.meeting.delete({ where: { id: meeting.id } });
  });

  it("creates a session with optional createdById FK", async () => {
    const user = await prisma.user.create({
      data: { email: "test-session@wizard.dev" },
    });
    const id = await createSession({ createdById: user.id });
    createdSessionIds.push(id);

    const session = await prisma.session.findUnique({ where: { id } });
    expect(session!.createdById).toBe(user.id);

    await prisma.session.delete({ where: { id } });
    await prisma.user.delete({ where: { id: user.id } });
  });
});

describe("endSession", () => {
  it("sets status to ENDED and stamps endedAt", async () => {
    const id = await createSession();
    createdSessionIds.push(id);

    await endSession(id);

    const fresh = new PrismaClient();
    const session = await fresh.session.findUnique({ where: { id } });
    await fresh.$disconnect();

    expect(session!.status).toBe("ENDED");
    expect(session!.endedAt).toBeInstanceOf(Date);
  });
});

describe("attachTaskToSession", () => {
  it("links a task to a session via SessionTask join table", async () => {
    const sessionId = await createSession();
    createdSessionIds.push(sessionId);

    const task = await prisma.task.create({
      data: { title: "Test task", status: "TODO", taskType: "CODING" },
    });
    createdTaskIds.push(task.id);

    await attachTaskToSession(sessionId, task.id);

    const session = await getSession(sessionId);
    expect(session!.tasks).toHaveLength(1);
    expect(session!.tasks[0].taskId).toBe(task.id);
  });
});

describe("crash durability", () => {
  it("session state is retrievable after simulated crash (new PrismaClient)", async () => {
    const id = await createSession();
    createdSessionIds.push(id);

    // Simulate crash: entirely new connection
    const afterCrash = new PrismaClient();
    const session = await afterCrash.session.findUnique({ where: { id } });
    await afterCrash.$disconnect();

    expect(session).not.toBeNull();
    expect(session!.status).toBe("ACTIVE");
  });
});
```

- [ ] **Step 4.2: Run the test — verify it fails**

```bash
yarn test tests/unit/session.test.ts
```

Expected: `Error: Failed to resolve import "../../services/session.js"`

- [ ] **Step 4.3: Create `services/session.ts`**

```typescript
// services/session.ts
import { PrismaClient } from "../../generated/prisma/index.js";

const prisma = new PrismaClient();

export type CreateSessionOptions = {
  meetingId?: number;
  createdById?: number;
};

export async function createSession(
  options?: CreateSessionOptions,
): Promise<number> {
  const session = await prisma.session.create({
    data: {
      status: "ACTIVE",
      meetingId: options?.meetingId ?? null,
      createdById: options?.createdById ?? null,
    },
  });
  return session.id;
}

export async function endSession(sessionId: number): Promise<void> {
  await prisma.session.update({
    where: { id: sessionId },
    data: { status: "ENDED", endedAt: new Date() },
  });
}

export async function getSession(sessionId: number) {
  return prisma.session.findUnique({
    where: { id: sessionId },
    include: {
      tasks: {
        include: { task: true },
      },
    },
  });
}

export async function attachTaskToSession(
  sessionId: number,
  taskId: number,
): Promise<void> {
  await prisma.sessionTask.create({
    data: { sessionId, taskId },
  });
}
```

- [ ] **Step 4.4: Run the test — verify it passes**

```bash
yarn test tests/unit/session.test.ts
```

Expected:

```
✓ createSession > creates an ACTIVE session and returns its int ID
✓ createSession > creates a session with optional meetingId FK
✓ createSession > creates a session with optional createdById FK
✓ endSession > sets status to ENDED and stamps endedAt
✓ attachTaskToSession > links a task to a session via SessionTask join table
✓ crash durability > session state is retrievable after simulated crash (new PrismaClient)

Test Files  1 passed (1)
Tests       6 passed (6)
```

- [ ] **Step 4.5: Commit**

```bash
git add services/session.ts tests/unit/session.test.ts
git commit -m "feat: add session lifecycle to services/session"
```

---

## Task 5: `core/workflows/task-start.ts` + `services/workflow.ts`

**Files:**

- Create: `core/workflows/task-start.ts`
- Create: `services/workflow.ts`
- Create: `tests/unit/workflow.test.ts`

`core/workflows/task-start.ts` is the hardcoded workflow definition. It defines what context is needed and how to build the variable map. `services/workflow.ts` executes it. The variable map uses the new schema field names: `external_task_id` (not `jira_key`), `branch` (not `github_branch`).

---

- [ ] **Step 5.1: Create `core/workflows/task-start.ts`**

```typescript
// core/workflows/task-start.ts
import type { TaskContext } from "../../shared/types.js";
import type { Variables } from "../../services/inject.js";

/**
 * Builds the variable map for the task_start skill template from a TaskContext.
 * This is the hardcoded workflow definition — services execute it.
 *
 * Variable map uses schema field names:
 *   external_task_id (was jiraKey), branch (was githubBranch)
 */
export function buildTaskStartVariables(context: TaskContext): Variables {
  return {
    task_id: String(context.id),
    title: context.title,
    task_type: context.taskType,
    status: context.status,
    external_task_id: context.externalTaskId ?? "none",
    due_date: context.dueDate
      ? context.dueDate.toISOString().split("T")[0]
      : "none",
    context: JSON.stringify(context, null, 2),
  };
}
```

- [ ] **Step 5.2: Write the failing test for `workflow.ts`**

```typescript
// tests/unit/workflow.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { PrismaClient } from "../../generated/prisma/index.js";
import { runTaskStartWorkflow } from "../../services/workflow.js";

const prisma = new PrismaClient();
let taskId: number;
let repoId: number;

beforeAll(async () => {
  const repo = await prisma.repo.create({
    data: { name: "wizard", url: "https://github.com/test/wizard-workflow" },
  });
  repoId = repo.id;

  const task = await prisma.task.create({
    data: {
      title: "Implement auth",
      status: "IN_PROGRESS",
      taskType: "CODING",
      externalTaskId: "PD-99",
      branch: "feat/auth",
      repoId: repoId,
      dueDate: new Date("2026-05-01T00:00:00.000Z"),
    },
  });
  taskId = task.id;
});

afterAll(async () => {
  await prisma.task.delete({ where: { id: taskId } });
  await prisma.repo.delete({ where: { id: repoId } });
  await prisma.$disconnect();
});

describe("runTaskStartWorkflow", () => {
  it("returns a formatted prompt with no unresolved placeholders", async () => {
    const result = await runTaskStartWorkflow(taskId);

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/);
    expect(result.prompt).toContain("Implement auth");
    expect(result.prompt).toContain("CODING");
    expect(result.prompt).toContain("PD-99");
    expect(result.prompt).toContain("2026-05-01");
  });

  it("returns ok: false when task does not exist", async () => {
    const result = await runTaskStartWorkflow(999999);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.reason).toContain("not found");
  });

  it("prompt contains the full context as JSON with int ID", async () => {
    const result = await runTaskStartWorkflow(taskId);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    const parsed = JSON.parse(result.prompt.split("Context:\n")[1] ?? "{}");
    expect(parsed.id).toBe(taskId);
    expect(typeof parsed.id).toBe("number");
    expect(parsed.title).toBe("Implement auth");
    expect(parsed.externalTaskId).toBe("PD-99");
  });
});
```

- [ ] **Step 5.3: Run the test — verify it fails**

```bash
yarn test tests/unit/workflow.test.ts
```

Expected: `Error: Failed to resolve import "../../services/workflow.js"`

- [ ] **Step 5.4: Create `services/workflow.ts`**

```typescript
// services/workflow.ts
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { injectVariables } from "./inject.js";
import { runPreflight } from "./preflight.js";
import { getTaskContext } from "../data/repositories/task.js";
import { buildTaskStartVariables } from "../core/workflows/task-start.js";

export type WorkflowResult =
  | { ok: true; prompt: string }
  | { ok: false; reason: string };

export async function runTaskStartWorkflow(
  taskId: number,
): Promise<WorkflowResult> {
  const preflight = await runPreflight();
  if (!preflight.ok) {
    return { ok: false, reason: `Pre-flight failed: ${preflight.reason}` };
  }

  const context = await getTaskContext(taskId);
  if (!context) {
    return { ok: false, reason: `Task not found: ${taskId}` };
  }

  const template = readFileSync(
    join(process.cwd(), "llm/prompts/task_start.md"),
    "utf-8",
  );

  const variables = buildTaskStartVariables(context);
  const prompt = injectVariables(template, variables);

  return { ok: true, prompt };
}
```

- [ ] **Step 5.5: Run the test — verify it passes**

```bash
yarn test tests/unit/workflow.test.ts
```

Expected:

```
✓ runTaskStartWorkflow > returns a formatted prompt with no unresolved placeholders
✓ runTaskStartWorkflow > returns ok: false when task does not exist
✓ runTaskStartWorkflow > prompt contains the full context as JSON with int ID

Test Files  1 passed (1)
Tests       3 passed (3)
```

- [ ] **Step 5.6: Commit**

```bash
git add core/workflows/task-start.ts services/workflow.ts tests/unit/workflow.test.ts
git commit -m "feat: add task-start workflow and services/workflow"
```

---

## Task 6: MCP Tools — `session_start` and `task_start`

**Files:**

- Modify: `interfaces/mcp/index.ts`

---

- [ ] **Step 6.1: Update `interfaces/mcp/index.ts`**

Replace the full file content:

```typescript
// interfaces/mcp/index.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getTaskContext } from "../data/repositories/task.js";
import {
  createSession,
  endSession,
  attachTaskToSession,
} from "../services/session.js";
import { runTaskStartWorkflow } from "../services/workflow.js";

const server = new McpServer({
  name: "wizard",
  version: "0.2.0",
});

server.tool("health", "Get health of Wizard System", {}, async () => ({
  content: [{ type: "text", text: "OK" }],
}));

server.tool(
  "get_task_context",
  "Get the full context for a task by int ID. Returns task details, linked meeting, externalTaskId, branch, and repoId.",
  { task_id: z.number().describe("The Wizard task ID (int)") },
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

server.tool(
  "session_start",
  "Start a new Wizard session. Returns the session ID (int).",
  {
    meeting_id: z.number().optional().describe("Optional meeting ID (int) to associate with the session"),
    created_by_id: z.number().optional().describe("Optional user ID (int) of session creator"),
  },
  async ({ meeting_id, created_by_id }) => {
    const sessionId = await createSession({
      meetingId: meeting_id,
      createdById: created_by_id,
    });
    return {
      content: [{ type: "text", text: JSON.stringify({ sessionId }) }],
    };
  },
);

server.tool(
  "task_start",
  "Start work on a task within the current session. Runs pre-flight, loads context, and returns the prepared prompt.",
  {
    task_id: z.number().describe("The Wizard task ID (int)"),
    session_id: z.number().describe("The current session ID (int)"),
  },
  async ({ task_id, session_id }) => {
    await attachTaskToSession(session_id, task_id);

    const result = await runTaskStartWorkflow(task_id);
    if (!result.ok) {
      return {
        content: [{ type: "text", text: result.reason }],
        isError: true,
      };
    }

    return {
      content: [{ type: "text", text: result.prompt }],
    };
  },
);

server.tool(
  "session_end",
  "End the current Wizard session.",
  { session_id: z.number().describe("The session ID to end (int)") },
  async ({ session_id }) => {
    await endSession(session_id);
    return {
      content: [{ type: "text", text: `Session ${session_id} ended.` }],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
```

- [ ] **Step 6.2: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 6.3: Commit**

```bash
git add interfaces/mcp/index.ts
git commit -m "feat: add session_start, task_start, session_end MCP tools"
```

---

## Task 7: Contract Test — Step 2 Proof Criteria

**Files:**

- Create: `tests/contracts/services-to-llm.test.ts`

---

- [ ] **Step 7.1: Create `tests/contracts/services-to-llm.test.ts`**

```typescript
// tests/contracts/services-to-llm.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { PrismaClient } from "../../generated/prisma/index.js";
import { runTaskStartWorkflow } from "../../services/workflow.js";
import {
  createSession,
  endSession,
  getSession,
} from "../../services/session.js";
import { runPreflight } from "../../services/preflight.js";

const prisma = new PrismaClient();
let taskId: number;
let repoId: number;
let sessionId: number;

beforeAll(async () => {
  const repo = await prisma.repo.create({
    data: { name: "wizard", url: "https://github.com/test/wizard-contract" },
  });
  repoId = repo.id;

  const task = await prisma.task.create({
    data: {
      title: "Contract test task",
      status: "IN_PROGRESS",
      taskType: "CODING",
      externalTaskId: "PD-CONTRACT",
      branch: "feat/contract-test",
      repoId: repoId,
    },
  });
  taskId = task.id;
  sessionId = await createSession();
});

afterAll(async () => {
  await prisma.sessionTask.deleteMany({ where: { sessionId } });
  await prisma.session.delete({ where: { id: sessionId } });
  await prisma.task.delete({ where: { id: taskId } });
  await prisma.repo.delete({ where: { id: repoId } });
  await prisma.$disconnect();
});

describe("Services → LLM layer contract", () => {
  it("pre-flight passes before workflow invocation", async () => {
    const result = await runPreflight();
    expect(result.ok).toBe(true);
  });

  it("workflow returns a formatted prompt — pre-flight runs internally", async () => {
    const result = await runTaskStartWorkflow(taskId);

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error(result.reason);

    // No unresolved placeholders
    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/);
    // Task data is present — uses new schema field names
    expect(result.prompt).toContain("Contract test task");
    expect(result.prompt).toContain("PD-CONTRACT");
  });

  it("session state persists across a simulated crash", async () => {
    // Simulate crash: brand new PrismaClient with fresh connection
    const afterCrash = new PrismaClient();
    const session = await afterCrash.session.findUnique({
      where: { id: sessionId },
    });
    await afterCrash.$disconnect();

    expect(session).not.toBeNull();
    expect(session!.id).toBe(sessionId);
    expect(typeof session!.id).toBe("number");
    expect(session!.status).toBe("ACTIVE");
  });

  it("session transitions to ENDED after endSession", async () => {
    const newSessionId = await createSession();

    await endSession(newSessionId);

    const afterCrash = new PrismaClient();
    const session = await afterCrash.session.findUnique({
      where: { id: newSessionId },
    });
    await afterCrash.$disconnect();

    expect(session!.status).toBe("ENDED");
    expect(session!.endedAt).toBeInstanceOf(Date);

    await prisma.session.delete({ where: { id: newSessionId } });
  });
});
```

- [ ] **Step 7.2: Run the contract test — verify it passes**

```bash
yarn test tests/contracts/services-to-llm.test.ts
```

Expected:

```
✓ Services → LLM layer contract > pre-flight passes before workflow invocation
✓ Services → LLM layer contract > workflow returns a formatted prompt — pre-flight runs internally
✓ Services → LLM layer contract > session state persists across a simulated crash
✓ Services → LLM layer contract > session transitions to ENDED after endSession

Test Files  1 passed (1)
Tests       4 passed (4)
```

- [ ] **Step 7.3: Commit**

```bash
git add tests/contracts/services-to-llm.test.ts
git commit -m "test(contract): add services-to-llm contract test — step 2 proof passing"
```

---

## Task 8: Final Verification

---

- [ ] **Step 8.1: Run the full test suite**

```bash
yarn test
```

Expected:

```
Test Files  5 passed (5)
Tests       19+ passed
```

(Step 1 tests: 9. Step 2 new tests: inject x 5, preflight x 1, session x 6, workflow x 3, contract x 4 = 19 new. Total count may vary slightly depending on Step 1 suite.)

- [ ] **Step 8.2: TypeScript clean build**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 8.3: Step 2 proof criteria met**

From the spec:

> The LLM layer is invoked by services with prepared context. Pre-flight check passes before invocation. Session state persists across a simulated crash.

- `runPreflight()` passes — verified in `services-to-llm.test.ts`
- `runTaskStartWorkflow()` returns prepared prompt — verified with no unresolved placeholders and task data present
- Session state survives crash — re-queried via fresh PrismaClient in two separate tests
- All IDs are int (autoincrement), not string (cuid)
- All imports use `../../generated/prisma/index.js`, not `@prisma/client`
- `getTaskContext` imported from `data/repositories/task.js`
- Seed data uses new schema shape: `externalTaskId`, `branch`, `repoId`

- [ ] **Step 8.4: Final commit**

```bash
git add .
git commit -m "chore: step 2 complete — services-to-llm contract passing"
```

---

## Troubleshooting

**`runPreflight` fails with "pgvector extension not installed"**
Ensure the Docker image is `pgvector/pgvector:pg16` and that `prisma migrate dev` was run (Step 1 migration enables the extension).

**Workflow test fails with "Task not found"**
Confirm `DATABASE_URL` in `.env` matches the running Docker container. Run `docker-compose up -d` if the container stopped.

**`tsc --noEmit` fails on `core/` imports**
Confirm `core/**/*.ts` is in the `include` array in `tsconfig.json` (Task 1 of this step).

**Import errors for `@prisma/client`**
All Prisma imports must use `../../generated/prisma/index.js` (relative path to generated output), not `@prisma/client`. The generator is configured with `provider = "prisma-client"` and `output = "../generated/prisma"`.
