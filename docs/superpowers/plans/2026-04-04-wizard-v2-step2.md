# Wizard v2 Step 2 — Orchestration → Data → Claude Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Orchestration layer — variable injection, pre-flight check, session lifecycle, and workflow execution — and prove that Claude is invoked with prepared context, pre-flight passes before invocation, and session state survives a simulated crash.

**Architecture:** Orchestration sits between Data and Claude. It reads context from Postgres, resolves skill template variables, runs a pre-flight check (Postgres reachable + pgvector installed), and produces a formatted prompt for Claude. Session state is written to Postgres before any Claude invocation — making it crash-durable by design. Workflow definitions live in `core/workflows/`; Orchestration executes them, never defines them.

**Tech Stack:** TypeScript (ESM, Node16), Prisma, Vitest. No new dependencies beyond Step 1.

> **PREREQUISITE — Serena Spike:** The spec requires Serena to be invoked deterministically by Orchestration (not by Claude at runtime). Before implementing Step 2, complete Task 0 below. Do not proceed past Task 0 until the spike is documented and the invocation pattern is confirmed.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `orchestrator/inject.ts` | Variable injection — replaces `{{key}}` placeholders; throws on unresolved |
| Create | `orchestrator/preflight.ts` | Pre-flight check — Postgres reachable + pgvector installed |
| Create | `orchestrator/session.ts` | Session lifecycle — create, attach task, end, re-query |
| Create | `orchestrator/workflow.ts` | Workflow execution — runs task_start, returns formatted prompt |
| Create | `core/workflows/task-start.ts` | Hardcoded task_start workflow definition |
| Modify | `mcp/index.ts` | Add `session_start` and `task_start` MCP tools |
| Modify | `tsconfig.json` | Add `orchestrator/**/*.ts` and `core/**/*.ts` to `include` |
| Create | `tests/unit/inject.test.ts` | Unit test for `injectVariables` (migrated from inline test) |
| Create | `tests/contracts/orchestration-to-claude.test.ts` | Step 2 proof criteria |

---

## Task 0: Serena Spike (Prerequisite)

**This task must be completed before any other task in this step.**

The spec states: *"Serena deterministic invocation — spike needed before Step 2. Unresolved. Do not proceed to Step 2 without this."*

Serena is an MCP server providing code intelligence (symbol lookup, file search, grep). In v1, Claude decides when to call it. In v2, Orchestration must call it programmatically — before Claude sees any context — so the result is deterministic and auditable.

---

- [ ] **Step 0.1: Understand Serena's MCP interface**

Run the following to list what tools Serena exposes:

```bash
# If Serena is configured as an MCP server in Claude Code, check its config:
cat ~/.claude/settings.json | grep -A 20 serena

# Also check the project-level Serena config:
cat .serena/project.json 2>/dev/null || echo "(no project config)"
```

Expected: a list of Serena MCP tools (e.g., `find_symbol`, `get_symbols_overview`, `search_for_pattern`, `list_dir`).

- [ ] **Step 0.2: Confirm programmatic MCP client invocation**

Serena runs as an MCP server. To call it from TypeScript code, use `@modelcontextprotocol/sdk`'s client:

```typescript
// Prototype — do not commit, just confirm it works
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

const transport = new StdioClientTransport({
  command: 'serena',       // adjust to actual Serena binary/command
  args: [],
})
const client = new Client({ name: 'wizard-spike', version: '0.0.1' })
await client.connect(transport)

const result = await client.callTool({ name: 'find_symbol', arguments: { name: 'TaskContext' } })
console.log(result)

await client.close()
```

Run this prototype. If it works, the invocation pattern is confirmed.

- [ ] **Step 0.3: Document the spike result**

Create `docs/spikes/serena-invocation.md`:

```markdown
# Serena Deterministic Invocation — Spike Result

## Serena command
[exact command/binary used]

## Working prototype
[paste the working TypeScript snippet]

## Tools used in Wizard
| Tool | Purpose |
|---|---|
| find_symbol | Locate a function/class by name in the codebase |
| get_symbols_overview | List symbols in a file |
| search_for_pattern | Regex search across files |

## Known constraints
[any timeouts, errors, or limitations discovered]

## Decision
[confirmed approach for integrations/serena/invoke.ts in Step 5]
```

- [ ] **Step 0.4: Commit the spike doc**

```bash
git add docs/spikes/serena-invocation.md
git commit -m "docs: serena invocation spike — step 2 prerequisite"
```

Only proceed past this point once the spike doc exists and the invocation pattern is confirmed.

---

## Task 1: `tsconfig.json` — Add New Directories

**Files:**
- Modify: `tsconfig.json`

---

- [ ] **Step 1.1: Add `orchestrator` and `core` to `tsconfig.json` include**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "Node16",
    "moduleResolution": "Node16",
    "outDir": "./build",
    "rootDir": ".",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": [
    "data/**/*.ts",
    "mcp/**/*.ts",
    "shared/**/*.ts",
    "integrations/**/*.ts",
    "orchestrator/**/*.ts",
    "core/**/*.ts"
  ],
  "exclude": [
    "node_modules",
    "build",
    "tests"
  ]
}
```

- [ ] **Step 1.2: Create directory skeleton**

```bash
mkdir -p orchestrator core/workflows docs/spikes
```

- [ ] **Step 1.3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 1.4: Commit**

```bash
git add tsconfig.json
git commit -m "chore: add orchestrator/ and core/ to tsconfig"
```

---

## Task 2: `orchestrator/inject.ts` — Variable Injection

**Files:**
- Create: `orchestrator/inject.ts`
- Create: `tests/unit/inject.test.ts`
- Modify: `tests/unit/skill-injection.test.ts` (update import)

The `injectVariables` function was inlined in the Step 1 unit test. It now moves to its permanent home in `orchestrator/`. The unit test is updated to import from there.

---

- [ ] **Step 2.1: Write the failing test**

```typescript
// tests/unit/inject.test.ts
import { describe, it, expect } from 'vitest'
import { injectVariables } from '../../orchestrator/inject.js'

describe('injectVariables', () => {
  it('replaces all placeholders with their values', () => {
    const result = injectVariables('Hello {{name}}, your task is {{task}}', {
      name: 'Kiran',
      task: 'implement auth',
    })
    expect(result).toBe('Hello Kiran, your task is implement auth')
  })

  it('throws when a placeholder has no matching variable', () => {
    expect(() => injectVariables('Hello {{name}}', {})).toThrow(
      'Unresolved placeholders: {{name}}'
    )
  })

  it('throws listing all unresolved placeholders', () => {
    expect(() =>
      injectVariables('{{a}} and {{b}} and {{c}}', { a: 'x' })
    ).toThrow('Unresolved placeholders: {{b}}, {{c}}')
  })

  it('handles a template with no placeholders', () => {
    const result = injectVariables('No placeholders here.', {})
    expect(result).toBe('No placeholders here.')
  })

  it('replaces multiple occurrences of the same placeholder', () => {
    const result = injectVariables('{{x}} and {{x}}', { x: 'hello' })
    expect(result).toBe('hello and hello')
  })
})
```

- [ ] **Step 2.2: Run the test — verify it fails**

```bash
yarn test tests/unit/inject.test.ts
```

Expected: `Error: Failed to resolve import "../../orchestrator/inject.js"`

- [ ] **Step 2.3: Create `orchestrator/inject.ts`**

```typescript
// orchestrator/inject.ts

export type Variables = Record<string, string>

/**
 * Replaces {{key}} placeholders in a template with values from the variables map.
 * Throws if any placeholder remains unresolved after substitution.
 */
export function injectVariables(template: string, variables: Variables): string {
  let result = template
  for (const [key, value] of Object.entries(variables)) {
    result = result.replaceAll(`{{${key}}}`, value)
  }
  const unresolved = result.match(/\{\{[^}]+\}\}/g)
  if (unresolved) {
    throw new Error(`Unresolved placeholders: ${unresolved.join(', ')}`)
  }
  return result
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

- [ ] **Step 2.5: Update `tests/unit/skill-injection.test.ts` to import from orchestrator**

Replace the inline `injectVariables` function at the top of the file with an import:

```typescript
// tests/unit/skill-injection.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { injectVariables } from '../../orchestrator/inject.js'

// Remove the inline injectVariables function — it now lives in orchestrator/inject.ts

const TASK_START_PATH = join(process.cwd(), 'plugin/skills/task_start.md')

const TASK_START_VARIABLES: Record<string, string> = {
  task_id: 'clxyz123',
  title: 'Add authentication',
  task_type: 'CODING',
  status: 'IN_PROGRESS',
  jira_key: 'PD-42',
  due_date: '2026-04-10T00:00:00.000Z',
  context: JSON.stringify({ id: 'clxyz123', title: 'Add authentication' }),
}

describe('task_start skill variable injection', () => {
  it('resolves all placeholders when given a complete variable map', () => {
    const template = readFileSync(TASK_START_PATH, 'utf-8')
    const result = injectVariables(template, TASK_START_VARIABLES)

    expect(result).not.toMatch(/\{\{[^}]+\}\}/)
    expect(result).toContain('clxyz123')
    expect(result).toContain('Add authentication')
    expect(result).toContain('CODING')
    expect(result).toContain('IN_PROGRESS')
    expect(result).toContain('PD-42')
  })

  it('contains exactly the expected placeholders and no others', () => {
    const template = readFileSync(TASK_START_PATH, 'utf-8')
    const found = [...template.matchAll(/\{\{([^}]+)\}\}/g)].map((m) => m[1])
    const expected = Object.keys(TASK_START_VARIABLES)

    expect(found.sort()).toEqual(expected.sort())
  })

  it('throws when a placeholder is not in the variable map', () => {
    const template = 'Hello {{name}}'
    expect(() => injectVariables(template, {})).toThrow(
      'Unresolved placeholders: {{name}}'
    )
  })

  it('throws when variables are missing from a partial map', () => {
    const template = readFileSync(TASK_START_PATH, 'utf-8')
    const partial = { task_id: 'clxyz123', title: 'Add authentication' }

    expect(() => injectVariables(template, partial)).toThrow('Unresolved placeholders')
  })
})
```

- [ ] **Step 2.6: Run the full unit test suite**

```bash
yarn test tests/unit/
```

Expected: all tests pass (both `inject.test.ts` and `skill-injection.test.ts`).

- [ ] **Step 2.7: Commit**

```bash
git add orchestrator/inject.ts tests/unit/inject.test.ts tests/unit/skill-injection.test.ts
git commit -m "feat: add injectVariables to orchestrator/inject"
```

---

## Task 3: `orchestrator/preflight.ts` — Pre-Flight Check

**Files:**
- Create: `orchestrator/preflight.ts`
- Create: `tests/unit/preflight.test.ts`

---

- [ ] **Step 3.1: Write the failing test**

```typescript
// tests/unit/preflight.test.ts
import { describe, it, expect } from 'vitest'
import { runPreflight } from '../../orchestrator/preflight.js'

describe('runPreflight', () => {
  it('returns ok: true when Postgres is reachable and pgvector is installed', async () => {
    // Requires: docker-compose up -d and DATABASE_URL set
    const result = await runPreflight()
    expect(result.ok).toBe(true)
  })
})
```

- [ ] **Step 3.2: Run the test — verify it fails**

```bash
yarn test tests/unit/preflight.test.ts
```

Expected: `Error: Failed to resolve import "../../orchestrator/preflight.js"`

- [ ] **Step 3.3: Create `orchestrator/preflight.ts`**

```typescript
// orchestrator/preflight.ts
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

export type PreflightResult =
  | { ok: true }
  | { ok: false; reason: string }

/**
 * Checks that Postgres is reachable and the pgvector extension is installed.
 * Must pass before any Claude invocation.
 */
export async function runPreflight(): Promise<PreflightResult> {
  try {
    await prisma.$queryRaw`SELECT 1`
  } catch (err) {
    return { ok: false, reason: `Postgres unreachable: ${String(err)}` }
  }

  const rows = await prisma.$queryRaw<{ count: bigint }[]>`
    SELECT count(*) AS count
    FROM pg_extension
    WHERE extname = 'vector'
  `
  if (Number(rows[0].count) === 0) {
    return { ok: false, reason: 'pgvector extension not installed' }
  }

  return { ok: true }
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
git add orchestrator/preflight.ts tests/unit/preflight.test.ts
git commit -m "feat: add runPreflight to orchestrator/preflight"
```

---

## Task 4: `orchestrator/session.ts` — Session Lifecycle

**Files:**
- Create: `orchestrator/session.ts`
- Create: `tests/unit/session.test.ts`

---

- [ ] **Step 4.1: Write the failing test**

```typescript
// tests/unit/session.test.ts
import { describe, it, expect, afterEach } from 'vitest'
import { PrismaClient } from '@prisma/client'
import {
  createSession,
  endSession,
  getSession,
  attachTaskToSession,
} from '../../orchestrator/session.js'

const prisma = new PrismaClient()
const createdSessionIds: string[] = []
const createdTaskIds: string[] = []

afterEach(async () => {
  // Clean up in FK order
  for (const id of createdSessionIds) {
    await prisma.sessionTask.deleteMany({ where: { sessionId: id } }).catch(() => {})
    await prisma.session.delete({ where: { id } }).catch(() => {})
  }
  for (const id of createdTaskIds) {
    await prisma.task.delete({ where: { id } }).catch(() => {})
  }
  createdSessionIds.length = 0
  createdTaskIds.length = 0
  await prisma.$disconnect()
})

describe('createSession', () => {
  it('creates an ACTIVE session and returns its ID', async () => {
    const id = await createSession()
    createdSessionIds.push(id)

    // Re-query with a fresh client to prove it is in Postgres (not in-memory)
    const fresh = new PrismaClient()
    const session = await fresh.session.findUnique({ where: { id } })
    await fresh.$disconnect()

    expect(session).not.toBeNull()
    expect(session!.status).toBe('ACTIVE')
    expect(session!.startedAt).toBeInstanceOf(Date)
    expect(session!.endedAt).toBeNull()
  })
})

describe('endSession', () => {
  it('sets status to ENDED and stamps endedAt', async () => {
    const id = await createSession()
    createdSessionIds.push(id)

    await endSession(id)

    const fresh = new PrismaClient()
    const session = await fresh.session.findUnique({ where: { id } })
    await fresh.$disconnect()

    expect(session!.status).toBe('ENDED')
    expect(session!.endedAt).toBeInstanceOf(Date)
  })
})

describe('attachTaskToSession', () => {
  it('links a task to a session', async () => {
    const sessionId = await createSession()
    createdSessionIds.push(sessionId)

    const task = await prisma.task.create({
      data: { title: 'Test task', status: 'TODO', taskType: 'CODING' },
    })
    createdTaskIds.push(task.id)

    await attachTaskToSession(sessionId, task.id)

    const session = await getSession(sessionId)
    expect(session!.tasks).toHaveLength(1)
    expect(session!.tasks[0].taskId).toBe(task.id)
  })
})

describe('crash durability', () => {
  it('session state is retrievable after simulated crash (new PrismaClient)', async () => {
    const id = await createSession()
    createdSessionIds.push(id)

    // Simulate crash: entirely new connection
    const afterCrash = new PrismaClient()
    const session = await afterCrash.session.findUnique({ where: { id } })
    await afterCrash.$disconnect()

    expect(session).not.toBeNull()
    expect(session!.status).toBe('ACTIVE')
  })
})
```

- [ ] **Step 4.2: Run the test — verify it fails**

```bash
yarn test tests/unit/session.test.ts
```

Expected: `Error: Failed to resolve import "../../orchestrator/session.js"`

- [ ] **Step 4.3: Create `orchestrator/session.ts`**

```typescript
// orchestrator/session.ts
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

export async function createSession(): Promise<string> {
  const session = await prisma.session.create({
    data: { status: 'ACTIVE' },
  })
  return session.id
}

export async function endSession(sessionId: string): Promise<void> {
  await prisma.session.update({
    where: { id: sessionId },
    data: { status: 'ENDED', endedAt: new Date() },
  })
}

export async function getSession(sessionId: string) {
  return prisma.session.findUnique({
    where: { id: sessionId },
    include: {
      tasks: {
        include: { task: true },
      },
    },
  })
}

export async function attachTaskToSession(
  sessionId: string,
  taskId: string
): Promise<void> {
  await prisma.sessionTask.create({
    data: { sessionId, taskId },
  })
}
```

- [ ] **Step 4.4: Run the test — verify it passes**

```bash
yarn test tests/unit/session.test.ts
```

Expected:

```
✓ createSession > creates an ACTIVE session and returns its ID
✓ endSession > sets status to ENDED and stamps endedAt
✓ attachTaskToSession > links a task to a session
✓ crash durability > session state is retrievable after simulated crash (new PrismaClient)

Test Files  1 passed (1)
Tests       4 passed (4)
```

- [ ] **Step 4.5: Commit**

```bash
git add orchestrator/session.ts tests/unit/session.test.ts
git commit -m "feat: add session lifecycle to orchestrator/session"
```

---

## Task 5: `core/workflows/task-start.ts` + `orchestrator/workflow.ts`

**Files:**
- Create: `core/workflows/task-start.ts`
- Create: `orchestrator/workflow.ts`
- Create: `tests/unit/workflow.test.ts`

`core/workflows/task-start.ts` is the hardcoded workflow definition. It defines what context is needed and how to build the variable map. `orchestrator/workflow.ts` executes it.

---

- [ ] **Step 5.1: Create `core/workflows/task-start.ts`**

```typescript
// core/workflows/task-start.ts
import type { TaskContext } from '../../shared/types.js'
import type { Variables } from '../../orchestrator/inject.js'

/**
 * Builds the variable map for the task_start skill template from a TaskContext.
 * This is the hardcoded workflow definition — Orchestration executes it.
 */
export function buildTaskStartVariables(context: TaskContext): Variables {
  return {
    task_id: context.id,
    title: context.title,
    task_type: context.taskType,
    status: context.status,
    jira_key: context.jiraKey ?? 'none',
    due_date: context.dueDate
      ? context.dueDate.toISOString().split('T')[0]
      : 'none',
    context: JSON.stringify(context, null, 2),
  }
}
```

- [ ] **Step 5.2: Write the failing test for `workflow.ts`**

```typescript
// tests/unit/workflow.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { PrismaClient } from '@prisma/client'
import { runTaskStartWorkflow } from '../../orchestrator/workflow.js'

const prisma = new PrismaClient()
let taskId: string

beforeAll(async () => {
  const task = await prisma.task.create({
    data: {
      title: 'Implement auth',
      status: 'IN_PROGRESS',
      taskType: 'CODING',
      jiraKey: 'PD-99',
      dueDate: new Date('2026-05-01T00:00:00.000Z'),
    },
  })
  taskId = task.id
})

afterAll(async () => {
  await prisma.task.delete({ where: { id: taskId } })
  await prisma.$disconnect()
})

describe('runTaskStartWorkflow', () => {
  it('returns a formatted prompt with no unresolved placeholders', async () => {
    const result = await runTaskStartWorkflow(taskId)

    expect(result.ok).toBe(true)
    if (!result.ok) return

    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/)
    expect(result.prompt).toContain('Implement auth')
    expect(result.prompt).toContain('CODING')
    expect(result.prompt).toContain('PD-99')
    expect(result.prompt).toContain('2026-05-01')
  })

  it('returns ok: false when task does not exist', async () => {
    const result = await runTaskStartWorkflow('nonexistent-task-id')
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('not found')
  })

  it('prompt contains the full context as JSON', async () => {
    const result = await runTaskStartWorkflow(taskId)
    expect(result.ok).toBe(true)
    if (!result.ok) return

    const parsed = JSON.parse(
      result.prompt.split('Context:\n')[1] ?? '{}'
    )
    expect(parsed.id).toBe(taskId)
    expect(parsed.title).toBe('Implement auth')
  })
})
```

- [ ] **Step 5.3: Run the test — verify it fails**

```bash
yarn test tests/unit/workflow.test.ts
```

Expected: `Error: Failed to resolve import "../../orchestrator/workflow.js"`

- [ ] **Step 5.4: Create `orchestrator/workflow.ts`**

```typescript
// orchestrator/workflow.ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { injectVariables } from './inject.js'
import { runPreflight } from './preflight.js'
import { getTaskContext } from '../data/queries/index.js'
import { buildTaskStartVariables } from '../core/workflows/task-start.js'

export type WorkflowResult =
  | { ok: true; prompt: string }
  | { ok: false; reason: string }

export async function runTaskStartWorkflow(taskId: string): Promise<WorkflowResult> {
  const preflight = await runPreflight()
  if (!preflight.ok) {
    return { ok: false, reason: `Pre-flight failed: ${preflight.reason}` }
  }

  const context = await getTaskContext(taskId)
  if (!context) {
    return { ok: false, reason: `Task not found: ${taskId}` }
  }

  const template = readFileSync(
    join(process.cwd(), 'plugin/skills/task_start.md'),
    'utf-8'
  )

  const variables = buildTaskStartVariables(context)
  const prompt = injectVariables(template, variables)

  return { ok: true, prompt }
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
✓ runTaskStartWorkflow > prompt contains the full context as JSON

Test Files  1 passed (1)
Tests       3 passed (3)
```

- [ ] **Step 5.6: Commit**

```bash
git add core/workflows/task-start.ts orchestrator/workflow.ts tests/unit/workflow.test.ts
git commit -m "feat: add task-start workflow and orchestrator/workflow"
```

---

## Task 6: MCP Tools — `session_start` and `task_start`

**Files:**
- Modify: `mcp/index.ts`

---

- [ ] **Step 6.1: Update `mcp/index.ts`**

Replace the full file content:

```typescript
// mcp/index.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { z } from 'zod'
import { getTaskContext } from '../data/queries/index.js'
import { createSession, endSession, attachTaskToSession } from '../orchestrator/session.js'
import { runTaskStartWorkflow } from '../orchestrator/workflow.js'

const server = new McpServer({
  name: 'wizard',
  version: '0.2.0',
})

server.tool(
  'health',
  'Get health of Wizard System',
  {},
  async () => ({
    content: [{ type: 'text', text: 'OK' }],
  })
)

server.tool(
  'get_task_context',
  'Get the full context for a task by ID. Returns task details, linked meeting, Jira key, and GitHub branch.',
  { task_id: z.string().describe('The Wizard task ID (cuid)') },
  async ({ task_id }) => {
    const context = await getTaskContext(task_id)
    if (!context) {
      return {
        content: [{ type: 'text', text: `Task not found: ${task_id}` }],
        isError: true,
      }
    }
    return {
      content: [{ type: 'text', text: JSON.stringify(context, null, 2) }],
    }
  }
)

server.tool(
  'session_start',
  'Start a new Wizard session. Returns the session ID.',
  {},
  async () => {
    const sessionId = await createSession()
    return {
      content: [{ type: 'text', text: JSON.stringify({ sessionId }) }],
    }
  }
)

server.tool(
  'task_start',
  'Start work on a task within the current session. Runs pre-flight, loads context, and returns the prepared prompt.',
  {
    task_id: z.string().describe('The Wizard task ID (cuid)'),
    session_id: z.string().describe('The current session ID'),
  },
  async ({ task_id, session_id }) => {
    await attachTaskToSession(session_id, task_id)

    const result = await runTaskStartWorkflow(task_id)
    if (!result.ok) {
      return {
        content: [{ type: 'text', text: result.reason }],
        isError: true,
      }
    }

    return {
      content: [{ type: 'text', text: result.prompt }],
    }
  }
)

server.tool(
  'session_end',
  'End the current Wizard session.',
  { session_id: z.string().describe('The session ID to end') },
  async ({ session_id }) => {
    await endSession(session_id)
    return {
      content: [{ type: 'text', text: `Session ${session_id} ended.` }],
    }
  }
)

const transport = new StdioServerTransport()
await server.connect(transport)
```

- [ ] **Step 6.2: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 6.3: Commit**

```bash
git add mcp/index.ts
git commit -m "feat: add session_start, task_start, session_end MCP tools"
```

---

## Task 7: Contract Test — Step 2 Proof Criteria

**Files:**
- Create: `tests/contracts/orchestration-to-claude.test.ts`

---

- [ ] **Step 7.1: Create `tests/contracts/orchestration-to-claude.test.ts`**

```typescript
// tests/contracts/orchestration-to-claude.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { PrismaClient } from '@prisma/client'
import { runTaskStartWorkflow } from '../../orchestrator/workflow.js'
import { createSession, endSession, getSession } from '../../orchestrator/session.js'
import { runPreflight } from '../../orchestrator/preflight.js'

const prisma = new PrismaClient()
let taskId: string
let sessionId: string

beforeAll(async () => {
  const task = await prisma.task.create({
    data: {
      title: 'Contract test task',
      status: 'IN_PROGRESS',
      taskType: 'CODING',
      jiraKey: 'PD-CONTRACT',
    },
  })
  taskId = task.id
  sessionId = await createSession()
})

afterAll(async () => {
  await prisma.sessionTask.deleteMany({ where: { sessionId } })
  await prisma.session.delete({ where: { id: sessionId } })
  await prisma.task.delete({ where: { id: taskId } })
  await prisma.$disconnect()
})

describe('Orchestration → Claude contract', () => {
  it('pre-flight passes before workflow invocation', async () => {
    const result = await runPreflight()
    expect(result.ok).toBe(true)
  })

  it('workflow returns a formatted prompt — pre-flight runs internally', async () => {
    const result = await runTaskStartWorkflow(taskId)

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error(result.reason)

    // No unresolved placeholders
    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/)
    // Task data is present
    expect(result.prompt).toContain('Contract test task')
    expect(result.prompt).toContain('PD-CONTRACT')
  })

  it('session state persists across a simulated crash', async () => {
    // Simulate crash: brand new PrismaClient with fresh connection
    const afterCrash = new PrismaClient()
    const session = await afterCrash.session.findUnique({
      where: { id: sessionId },
    })
    await afterCrash.$disconnect()

    expect(session).not.toBeNull()
    expect(session!.id).toBe(sessionId)
    expect(session!.status).toBe('ACTIVE')
  })

  it('session transitions to ENDED after endSession', async () => {
    const newSessionId = await createSession()

    await endSession(newSessionId)

    const afterCrash = new PrismaClient()
    const session = await afterCrash.session.findUnique({
      where: { id: newSessionId },
    })
    await afterCrash.$disconnect()

    expect(session!.status).toBe('ENDED')
    expect(session!.endedAt).toBeInstanceOf(Date)

    await prisma.session.delete({ where: { id: newSessionId } })
  })
})
```

- [ ] **Step 7.2: Run the contract test — verify it passes**

```bash
yarn test tests/contracts/orchestration-to-claude.test.ts
```

Expected:

```
✓ Orchestration → Claude contract > pre-flight passes before workflow invocation
✓ Orchestration → Claude contract > workflow returns a formatted prompt — pre-flight runs internally
✓ Orchestration → Claude contract > session state persists across a simulated crash
✓ Orchestration → Claude contract > session transitions to ENDED after endSession

Test Files  1 passed (1)
Tests       4 passed (4)
```

- [ ] **Step 7.3: Commit**

```bash
git add tests/contracts/orchestration-to-claude.test.ts
git commit -m "test(contract): add orchestration-to-claude contract test — step 2 proof passing"
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
Test Files  4 passed (4)
Tests       17 passed (17)
```

(Step 1 tests: 9. Step 2 new tests: inject × 5, preflight × 1, session × 4, workflow × 3, contract × 4 = 17 new. But some run together so count may vary slightly.)

- [ ] **Step 8.2: TypeScript clean build**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 8.3: Step 2 proof criteria met**

From the spec:

> Claude is invoked by Orchestration with prepared context. Pre-flight check passes before invocation. Session state persists across a simulated crash.

- `runPreflight()` passes ✓ — verified in `orchestration-to-claude.test.ts`
- `runTaskStartWorkflow()` returns prepared prompt ✓ — verified with no unresolved placeholders and task data present
- Session state survives crash ✓ — re-queried via fresh PrismaClient in two separate tests

- [ ] **Step 8.4: Final commit**

```bash
git add .
git commit -m "chore: step 2 complete — orchestration-to-claude contract passing"
```

---

## Troubleshooting

**`runPreflight` fails with "pgvector extension not installed"**
Ensure the Docker image is `pgvector/pgvector:pg16` and that `prisma migrate dev` was run (Step 1 migration enables the extension).

**Workflow test fails with "Task not found"**
Confirm `DATABASE_URL` in `.env` matches the running Docker container. Run `docker-compose up -d` if the container stopped.

**`tsc --noEmit` fails on `core/` imports**
Confirm `core/**/*.ts` is in the `include` array in `tsconfig.json` (Task 1 of this step).

**Serena spike fails — binary not found**
Check how Serena is installed: `which serena` or look at `.claude/settings.json` for the configured MCP command. The binary name may differ (e.g., `serena-mcp`, `python -m serena`).
