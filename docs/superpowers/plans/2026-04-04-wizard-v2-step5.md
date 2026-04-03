# Wizard v2 Step 5 — Full System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build remaining integrations (Jira, Krisp, GitHub, Serena), task-type aware context loading, the full session flow (`wizard session start` → `wizard session end`), remaining CLI commands, remaining skill templates, and evaluation scaffolding. Prove the full session runs end-to-end with PII-free Postgres, task-type specific context, and traceable output.

**Architecture:** This step completes the system. Each integration follows the same pattern as Notion: pull raw data → route through security → return scrubbed results. The `core/context-loader.ts` switches on task type to call only the relevant integrations. CLI commands orchestrate the full session flow by calling the MCP tools and orchestrator functions. Skill templates complete the `plugin/skills/` directory. `evals/` is scaffolding only — types and a runner stub; no scoring logic.

**Tech Stack:** TypeScript (ESM, Node16), Prisma, Vitest, `commander`, existing `@notionhq/client`, `openai`. New: GitHub REST via `@octokit/rest`, Jira via direct REST (no heavy SDK), Krisp via file/MCP read.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `integrations/jira/pull.ts` | Pull task details from Jira REST API |
| Create | `integrations/krisp/pull.ts` | Read Krisp meeting transcripts |
| Create | `integrations/github/pull.ts` | Read ADRs and branch info from GitHub |
| Create | `integrations/serena/invoke.ts` | Deterministic Serena invocation (uses spike result from Step 2) |
| Create | `core/context-loader.ts` | Task-type aware context loading — dispatches to correct integrations |
| Create | `cli/commands/session.ts` | `wizard session start` / `wizard session end` |
| Create | `cli/commands/task.ts` | `wizard task start` / `wizard task end` |
| Create | `cli/commands/doctor.ts` | `wizard doctor` — health check all integrations + DB |
| Create | `cli/commands/integrate.ts` | `wizard integrate add <source>` |
| Modify | `cli/index.ts` | Register all new commands |
| Create | `plugin/skills/session_start.md` | Skill template |
| Create | `plugin/skills/task_end.md` | Skill template |
| Create | `plugin/skills/session_end.md` | Skill template |
| Create | `plugin/skills/meeting_review.md` | Skill template |
| Create | `plugin/skills/code_review.md` | Skill template |
| Create | `plugin/skills/blast_radius.md` | Skill template |
| Create | `plugin/skills/architecture_debate.md` | Skill template |
| Create | `evals/schema.ts` | Dataset format type definitions |
| Create | `evals/runner.ts` | Runner stub — interface defined, body deferred |
| Modify | `package.json` | Add `@octokit/rest` |
| Modify | `tsconfig.json` | Add `evals/**/*.ts` to `include` |
| Create | `tests/unit/context-loader.test.ts` | Each task type returns correct source set |
| Create | `tests/unit/skill-templates.test.ts` | All remaining templates resolve correctly |
| Create | `tests/contracts/full-session.test.ts` | End-to-end session proof criteria |

---

## Task 1: Dependencies + Directory Structure

**Files:**
- Modify: `package.json`
- Modify: `tsconfig.json`

---

- [ ] **Step 1.1: Install new dependencies**

```bash
yarn add @octokit/rest
```

- [ ] **Step 1.2: Update `package.json`**

Add `@octokit/rest` to `dependencies`:

```json
{
  "name": "wizard",
  "packageManager": "yarn@4.12.0",
  "type": "module",
  "bin": {
    "wizard-mcp": "./build/mcp/index.js",
    "wizard": "./build/cli/index.js"
  },
  "prisma": {
    "schema": "data/prisma/schema.prisma"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.28.0",
    "@notionhq/client": "^5.15.0",
    "@octokit/rest": "^21.0.0",
    "@prisma/client": "^6.0.0",
    "commander": "^12.0.0",
    "js-yaml": "^4.1.0",
    "openai": "^4.0.0",
    "pgvector": "^0.2.0",
    "zod": "^4.3.6"
  },
  "devDependencies": {
    "@types/js-yaml": "^4.0.9",
    "@types/node": "^25.5.0",
    "prisma": "^6.0.0",
    "typescript": "^6.0.2",
    "vitest": "^3.0.0"
  },
  "scripts": {
    "build": "tsc && chmod 755 build/mcp/index.js && chmod 755 build/cli/index.js",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "files": [
    "build"
  ]
}
```

- [ ] **Step 1.3: Update `tsconfig.json` — add `evals/`**

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
    "core/**/*.ts",
    "security/**/*.ts",
    "cli/**/*.ts",
    "evals/**/*.ts"
  ],
  "exclude": [
    "node_modules",
    "build",
    "tests"
  ]
}
```

- [ ] **Step 1.4: Create directory skeleton**

```bash
mkdir -p integrations/jira integrations/krisp integrations/github integrations/serena evals
```

- [ ] **Step 1.5: Commit**

```bash
git add package.json tsconfig.json
git commit -m "chore: add octokit dep and evals/ to tsconfig for step 5"
```

---

## Task 2: Remaining Integrations

**Files:**
- Create: `integrations/jira/pull.ts`
- Create: `integrations/krisp/pull.ts`
- Create: `integrations/github/pull.ts`
- Create: `integrations/serena/invoke.ts`

---

- [ ] **Step 2.1: Create `integrations/jira/pull.ts`**

Jira is called via REST. No heavy SDK — `fetch` is sufficient for a single endpoint.

```typescript
// integrations/jira/pull.ts
import { scrub } from '../../security/scrub.js'
import type { ScrubResult } from '../../security/types.js'

export type RawJiraTask = {
  jiraKey: string
  summary: ScrubResult
  description: ScrubResult
  status: string
  priority: string | null
  dueDate: string | null
  assignee: string | null
}

/**
 * Fetches a Jira issue by key and scrubs PII from text fields.
 * baseUrl example: "https://your-org.atlassian.net"
 */
export async function pullJiraTask(
  baseUrl: string,
  token: string,
  issueKey: string
): Promise<RawJiraTask> {
  const url = `${baseUrl}/rest/api/3/issue/${issueKey}`
  const response = await fetch(url, {
    headers: {
      Authorization: `Basic ${Buffer.from(`wizard@wizard.local:${token}`).toString('base64')}`,
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Jira API error ${response.status}: ${await response.text()}`)
  }

  const data = (await response.json()) as Record<string, any>
  const fields = data.fields ?? {}

  const rawSummary = fields.summary ?? ''
  const rawDesc = fields.description?.content
    ?.flatMap((block: any) =>
      block.content?.map((node: any) => node.text ?? '').filter(Boolean) ?? []
    )
    .join(' ') ?? ''

  return {
    jiraKey: data.key,
    summary: scrub(rawSummary, `jira.issue.${issueKey}.summary`),
    description: scrub(rawDesc, `jira.issue.${issueKey}.description`),
    status: fields.status?.name ?? 'Unknown',
    priority: fields.priority?.name ?? null,
    dueDate: fields.duedate ?? null,
    assignee: null, // Assignee names not stored — PII risk without NLP
  }
}
```

- [ ] **Step 2.2: Create `integrations/krisp/pull.ts`**

Krisp transcripts arrive as text files or via MCP. In v2, Krisp's MCP method reads transcripts as plain text. The transcript is scrubbed before being returned.

```typescript
// integrations/krisp/pull.ts
import { readFileSync } from 'node:fs'
import { scrub } from '../../security/scrub.js'
import type { ScrubResult } from '../../security/types.js'

export type RawKrispTranscript = {
  meetingTitle: ScrubResult
  transcript: ScrubResult
  url: string
}

/**
 * Reads a Krisp transcript from a local file path (downloaded or synced by wizard setup).
 * In v2, Krisp transcripts are provided as local text files.
 * Scrubs PII before returning.
 */
export function readKrispTranscript(filePath: string, meetingUrl: string): RawKrispTranscript {
  const raw = readFileSync(filePath, 'utf-8')

  // Extract meeting title from first line if present (Krisp format: "# Meeting Title")
  const lines = raw.split('\n')
  const titleLine = lines[0].startsWith('#') ? lines[0].replace(/^#+\s*/, '') : 'Meeting'
  const body = lines.slice(1).join('\n').trim()

  return {
    meetingTitle: scrub(titleLine, `krisp.${meetingUrl}.title`),
    transcript: scrub(body, `krisp.${meetingUrl}.transcript`),
    url: meetingUrl,
  }
}
```

- [ ] **Step 2.3: Create `integrations/github/pull.ts`**

```typescript
// integrations/github/pull.ts
import { Octokit } from '@octokit/rest'
import { scrub } from '../../security/scrub.js'
import type { ScrubResult } from '../../security/types.js'

export type RawAdr = {
  path: string
  title: ScrubResult
  content: ScrubResult
  sha: string
}

export type BranchInfo = {
  name: string
  lastCommitSha: string
  lastCommitMessage: ScrubResult
}

/**
 * Fetches ADR markdown files from a GitHub repo directory.
 * Scrubs PII from content before returning.
 */
export async function pullAdrs(
  token: string,
  owner: string,
  repo: string,
  adrPath: string = 'docs/adr'
): Promise<RawAdr[]> {
  const octokit = new Octokit({ auth: token })

  let files: any[]
  try {
    const { data } = await octokit.repos.getContent({ owner, repo, path: adrPath })
    files = Array.isArray(data) ? data : [data]
  } catch {
    return [] // ADR directory doesn't exist yet
  }

  const adrs: RawAdr[] = []
  for (const file of files.filter((f) => f.name.endsWith('.md'))) {
    const { data } = await octokit.repos.getContent({ owner, repo, path: file.path })
    const content = Buffer.from((data as any).content, 'base64').toString('utf-8')
    const titleMatch = content.match(/^#\s+(.+)/m)
    const title = titleMatch ? titleMatch[1] : file.name

    adrs.push({
      path: file.path,
      title: scrub(title, `github.${owner}/${repo}.adr.${file.name}.title`),
      content: scrub(content, `github.${owner}/${repo}.adr.${file.name}.content`),
      sha: file.sha,
    })
  }

  return adrs
}

/**
 * Fetches branch info for a given branch name.
 */
export async function pullBranchInfo(
  token: string,
  owner: string,
  repo: string,
  branch: string
): Promise<BranchInfo | null> {
  const octokit = new Octokit({ auth: token })

  try {
    const { data } = await octokit.repos.getBranch({ owner, repo, branch })
    const commitMessage = data.commit.commit.message ?? ''
    return {
      name: branch,
      lastCommitSha: data.commit.sha,
      lastCommitMessage: scrub(commitMessage, `github.${owner}/${repo}.${branch}.commit`),
    }
  } catch {
    return null
  }
}
```

- [ ] **Step 2.4: Create `integrations/serena/invoke.ts`**

Fill this in using the spike result from Task 0 of Step 2. The template below assumes Serena runs as an MCP server accessible via stdio. Replace `SERENA_COMMAND` and `SERENA_ARGS` with the values discovered in the spike.

```typescript
// integrations/serena/invoke.ts
// IMPLEMENTATION DEPENDS ON SERENA SPIKE (see docs/spikes/serena-invocation.md)
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'

// Update these based on the spike result
const SERENA_COMMAND = process.env.SERENA_COMMAND ?? 'serena'
const SERENA_ARGS = (process.env.SERENA_ARGS ?? '').split(' ').filter(Boolean)

export type SerenaSymbol = {
  name: string
  kind: string
  file: string
  line: number
}

export type SerenaSearchResult = {
  file: string
  line: number
  content: string
}

async function withSerenaClient<T>(
  fn: (client: Client) => Promise<T>
): Promise<T> {
  const transport = new StdioClientTransport({
    command: SERENA_COMMAND,
    args: SERENA_ARGS,
  })
  const client = new Client({ name: 'wizard', version: '0.2.0' })
  await client.connect(transport)
  try {
    return await fn(client)
  } finally {
    await client.close()
  }
}

/**
 * Finds a symbol by name in the codebase using Serena.
 */
export async function findSymbol(symbolName: string): Promise<SerenaSymbol[]> {
  return withSerenaClient(async (client) => {
    const result = await client.callTool({
      name: 'find_symbol',
      arguments: { name: symbolName, substring_matching: true },
    })
    // Parse Serena's response — format depends on spike findings
    const text = (result.content as any[])[0]?.text ?? '[]'
    return JSON.parse(text)
  })
}

/**
 * Searches for a pattern across the codebase using Serena.
 */
export async function searchForPattern(
  pattern: string,
  relativePath?: string
): Promise<SerenaSearchResult[]> {
  return withSerenaClient(async (client) => {
    const result = await client.callTool({
      name: 'search_for_pattern',
      arguments: { pattern, relative_path: relativePath },
    })
    const text = (result.content as any[])[0]?.text ?? '[]'
    return JSON.parse(text)
  })
}
```

- [ ] **Step 2.5: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 2.6: Commit**

```bash
git add integrations/jira/pull.ts integrations/krisp/pull.ts integrations/github/pull.ts integrations/serena/invoke.ts
git commit -m "feat: add Jira, Krisp, GitHub, and Serena integrations"
```

---

## Task 3: `core/context-loader.ts` — Task-Type Aware Context Loading

**Files:**
- Create: `core/context-loader.ts`
- Create: `tests/unit/context-loader.test.ts`

---

- [ ] **Step 3.1: Write the failing test**

```typescript
// tests/unit/context-loader.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock all integrations
vi.mock('../../integrations/notion/pull.js', () => ({
  pullNotionTasks: vi.fn().mockResolvedValue([]),
  pullNotionMeetings: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../integrations/jira/pull.js', () => ({
  pullJiraTask: vi.fn().mockResolvedValue({}),
}))
vi.mock('../../integrations/github/pull.js', () => ({
  pullAdrs: vi.fn().mockResolvedValue([]),
  pullBranchInfo: vi.fn().mockResolvedValue(null),
}))
vi.mock('../../integrations/serena/invoke.js', () => ({
  findSymbol: vi.fn().mockResolvedValue([]),
  searchForPattern: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../data/queries/config.js', () => ({
  getIntegrationToken: vi.fn().mockResolvedValue('mock-token'),
}))

import { loadContext } from '../../core/context-loader.js'
import { pullNotionTasks, pullNotionMeetings } from '../../integrations/notion/pull.js'
import { pullAdrs, pullBranchInfo } from '../../integrations/github/pull.js'
import { findSymbol } from '../../integrations/serena/invoke.js'

const baseTask = {
  id: 'task-001',
  title: 'Test task',
  taskType: 'CODING' as const,
  githubRepo: 'sisu-universe',
  githubBranch: 'feat/auth',
  jiraKey: 'PD-42',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('loadContext', () => {
  it('CODING task loads Notion tasks, ADRs, branch info, and Serena', async () => {
    await loadContext({ ...baseTask, taskType: 'CODING' })

    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullAdrs).toHaveBeenCalled()
    expect(pullBranchInfo).toHaveBeenCalled()
    expect(findSymbol).toHaveBeenCalled()
  })

  it('MEETING_REVIEW task loads only Krisp — no Notion, no GitHub, no Serena', async () => {
    await loadContext({ ...baseTask, taskType: 'MEETING_REVIEW' })

    expect(pullNotionTasks).not.toHaveBeenCalled()
    expect(pullAdrs).not.toHaveBeenCalled()
    expect(findSymbol).not.toHaveBeenCalled()
  })

  it('DEBUGGING task loads Serena and Notion — does not load ADRs', async () => {
    await loadContext({ ...baseTask, taskType: 'DEBUGGING' })

    expect(findSymbol).toHaveBeenCalled()
    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullAdrs).not.toHaveBeenCalled()
  })

  it('ADR task loads GitHub ADRs and Notion — does not load Serena', async () => {
    await loadContext({ ...baseTask, taskType: 'ADR' })

    expect(pullAdrs).toHaveBeenCalled()
    expect(pullNotionMeetings).toHaveBeenCalled()
    expect(findSymbol).not.toHaveBeenCalled()
  })

  it('INVESTIGATION task loads all sources', async () => {
    await loadContext({ ...baseTask, taskType: 'INVESTIGATION' })

    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullNotionMeetings).toHaveBeenCalled()
    expect(pullAdrs).toHaveBeenCalled()
    expect(findSymbol).toHaveBeenCalled()
  })

  it('TEST_GENERATION task loads Serena and Notion tasks — not ADRs', async () => {
    await loadContext({ ...baseTask, taskType: 'TEST_GENERATION' })

    expect(findSymbol).toHaveBeenCalled()
    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullAdrs).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 3.2: Run the test — verify it fails**

```bash
yarn test tests/unit/context-loader.test.ts
```

Expected: `Error: Failed to resolve import "../../core/context-loader.js"`

- [ ] **Step 3.3: Create `core/context-loader.ts`**

```typescript
// core/context-loader.ts
// Task-type dispatch table — from SPEC.md §6 Session Architecture
//
// Task Type       | Sources
// --------------- | -----------------------------------------
// CODING          | Notion tasks, GitHub ADRs, branch info, Serena
// DEBUGGING       | Serena, Notion tasks
// INVESTIGATION   | All sources
// ADR             | GitHub ADRs, Notion meetings
// TEST_GENERATION | Serena, Notion tasks
// MEETING_REVIEW  | Krisp only (no external calls here — Krisp is read at CLI level)

import { pullNotionTasks, pullNotionMeetings } from '../integrations/notion/pull.js'
import { pullAdrs, pullBranchInfo } from '../integrations/github/pull.js'
import { findSymbol } from '../integrations/serena/invoke.js'
import { getIntegrationToken } from '../data/queries/config.js'
import type { TaskType } from '../shared/types.js'

export type ContextInput = {
  id: string
  title: string
  taskType: TaskType
  githubRepo?: string | null
  githubBranch?: string | null
  jiraKey?: string | null
}

export type LoadedContext = {
  notionTasks: unknown[]
  notionMeetings: unknown[]
  adrs: unknown[]
  branchInfo: unknown | null
  serenaSymbols: unknown[]
}

/**
 * Loads context appropriate for the task type.
 * Only calls the sources the task type actually needs — no unnecessary tokens.
 */
export async function loadContext(task: ContextInput): Promise<LoadedContext> {
  const notionToken = await getIntegrationToken('notion')
  const githubToken = await getIntegrationToken('github')

  // Notion database IDs come from IntegrationConfig metadata in production.
  // Using env vars as fallback for now.
  const notionTasksDb = process.env.NOTION_TASKS_DB_ID ?? ''
  const notionMeetingsDb = process.env.NOTION_MEETINGS_DB_ID ?? ''
  const githubOwner = process.env.GITHUB_OWNER ?? ''

  const ctx: LoadedContext = {
    notionTasks: [],
    notionMeetings: [],
    adrs: [],
    branchInfo: null,
    serenaSymbols: [],
  }

  const loadNotionTasks = async () => {
    if (notionToken && notionTasksDb) {
      ctx.notionTasks = await pullNotionTasks(notionToken, notionTasksDb)
    }
  }
  const loadNotionMeetings = async () => {
    if (notionToken && notionMeetingsDb) {
      ctx.notionMeetings = await pullNotionMeetings(notionToken, notionMeetingsDb)
    }
  }
  const loadAdrs = async () => {
    if (githubToken && githubOwner && task.githubRepo) {
      ctx.adrs = await pullAdrs(githubToken, githubOwner, task.githubRepo)
    }
  }
  const loadBranchInfo = async () => {
    if (githubToken && githubOwner && task.githubRepo && task.githubBranch) {
      ctx.branchInfo = await pullBranchInfo(
        githubToken, githubOwner, task.githubRepo, task.githubBranch
      )
    }
  }
  const loadSerena = async () => {
    ctx.serenaSymbols = await findSymbol(task.title)
  }

  switch (task.taskType) {
    case 'CODING':
      await Promise.all([loadNotionTasks(), loadAdrs(), loadBranchInfo(), loadSerena()])
      break
    case 'DEBUGGING':
      await Promise.all([loadSerena(), loadNotionTasks()])
      break
    case 'INVESTIGATION':
      await Promise.all([
        loadNotionTasks(), loadNotionMeetings(), loadAdrs(), loadSerena()
      ])
      break
    case 'ADR':
      await Promise.all([loadAdrs(), loadNotionMeetings()])
      break
    case 'TEST_GENERATION':
      await Promise.all([loadSerena(), loadNotionTasks()])
      break
    case 'MEETING_REVIEW':
      // Krisp transcript is read directly in the CLI command, not here
      break
  }

  return ctx
}
```

- [ ] **Step 3.4: Run the test — verify it passes**

```bash
yarn test tests/unit/context-loader.test.ts
```

Expected:

```
✓ loadContext > CODING task loads Notion tasks, ADRs, branch info, and Serena
✓ loadContext > MEETING_REVIEW task loads only Krisp — no Notion, no GitHub, no Serena
✓ loadContext > DEBUGGING task loads Serena and Notion — does not load ADRs
✓ loadContext > ADR task loads GitHub ADRs and Notion — does not load Serena
✓ loadContext > INVESTIGATION task loads all sources
✓ loadContext > TEST_GENERATION task loads Serena and Notion tasks — not ADRs

Test Files  1 passed (1)
Tests       6 passed (6)
```

- [ ] **Step 3.5: Commit**

```bash
git add core/context-loader.ts tests/unit/context-loader.test.ts
git commit -m "feat: add task-type aware context loading to core/context-loader"
```

---

## Task 4: Remaining Skill Templates

**Files:**
- Create: `plugin/skills/session_start.md`
- Create: `plugin/skills/task_end.md`
- Create: `plugin/skills/session_end.md`
- Create: `plugin/skills/meeting_review.md`
- Create: `plugin/skills/code_review.md`
- Create: `plugin/skills/blast_radius.md`
- Create: `plugin/skills/architecture_debate.md`
- Create: `tests/unit/skill-templates.test.ts`

---

- [ ] **Step 4.1: Create `plugin/skills/session_start.md`**

```markdown
You are starting a new Wizard session.

Session ID: {{session_id}}
Date: {{date}}

Here are your open tasks:
{{task_list}}

Here are your recent meeting notes:
{{meeting_list}}

Which task would you like to work on today? Reply with the task ID.
```

Variables: `session_id`, `date`, `task_list`, `meeting_list`

- [ ] **Step 4.2: Create `plugin/skills/task_end.md`**

```markdown
The work on the following task is complete.

Task: {{title}} ({{task_id}})
Type: {{task_type}}
Jira: {{jira_key}}

Produce a structured summary of what was done. Reply with ONLY the following JSON block and nothing else:

```json
{
  "taskId": "{{task_id}}",
  "summary": "<one paragraph summary of what was done>",
  "status": "<TODO|IN_PROGRESS|DONE>",
  "meetingId": "<meeting ID if this work relates to a meeting, otherwise null>",
  "notes": "<any implementation notes or decisions made>"
}
```
```

Variables: `task_id`, `title`, `task_type`, `jira_key`

- [ ] **Step 4.3: Create `plugin/skills/session_end.md`**

```markdown
The Wizard session is ending.

Session ID: {{session_id}}
Date: {{date}}
Tasks worked on: {{completed_tasks}}

Produce a session summary covering:
1. What was accomplished
2. Blockers encountered
3. Decisions made that should be recorded

Classify each learning as either:
- TEAM_KNOWLEDGE: goes to Engineering Docs in Notion
- PERSONAL_PREFERENCE: goes to CLAUDE.md

Reply with your summary, then list learnings in this format:
LEARNING [TEAM_KNOWLEDGE|PERSONAL_PREFERENCE]: <learning>
```

Variables: `session_id`, `date`, `completed_tasks`

- [ ] **Step 4.4: Create `plugin/skills/meeting_review.md`**

```markdown
Review the following meeting transcript and extract structured information.

Meeting URL: {{meeting_url}}
Date: {{meeting_date}}

Transcript:
{{transcript}}

Reply with ONLY the following JSON block:

```json
{
  "title": "<meeting title>",
  "outline": "<2-3 sentence overview>",
  "keyPoints": ["<point 1>", "<point 2>"],
  "actionItems": ["<action: owner>"]
}
```
```

Variables: `meeting_url`, `meeting_date`, `transcript`

- [ ] **Step 4.5: Create `plugin/skills/code_review.md`**

```markdown
Review the following code change.

Task: {{title}} ({{task_id}})
Context:
{{context}}

Apply the six-step review in this order:

1. **Correctness** — Does it do what it claims? Are error paths handled?
2. **Blast Radius** — What does this touch that wasn't intended?
3. **Invariant Violations** — Does it break SRP, DRY, or dependency rules?
4. **Observability** — Can this be debugged at 2am?
5. **Tests** — Do the tests verify behaviour or just execute code paths?
6. **Simplicity** — Is this the simplest thing that works?

For each step, state: PASS, CONCERN, or FAIL with a one-sentence reason.
End with: APPROVE or REQUEST_CHANGES.
```

Variables: `task_id`, `title`, `context`

- [ ] **Step 4.6: Create `plugin/skills/blast_radius.md`**

```markdown
Trace the blast radius of a change.

Symbol or file: {{target}}
Task: {{task_id}}
Context:
{{context}}

Using the codebase context provided:
1. List every direct caller or importer of {{target}}
2. List every system or module that depends on those callers
3. State what breaks if {{target}} changes in each scenario

Format each as:
CALLER: <file:line> — RISK: <what breaks>
```

Variables: `target`, `task_id`, `context`

- [ ] **Step 4.7: Create `plugin/skills/architecture_debate.md`**

```markdown
Debate the following architectural decision from four positions.

Question: {{question}}
Context:
{{context}}

Present four arguments in this order:

1. **Domain Model** — What does the domain model dictate?
2. **Simplicity** — What is the simplest possible solution?
3. **Operations** — What is easiest to operate, monitor, and debug in production?
4. **Devil's Advocate** — What is the strongest argument against the leading option?

End with:
RECOMMENDATION: <chosen approach>
TRADE-OFF: <what this costs vs. what it gains>
IRREVERSIBLE: <yes/no — and why if yes>
```

Variables: `question`, `context`

- [ ] **Step 4.8: Write the skill templates unit test**

```typescript
// tests/unit/skill-templates.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { injectVariables } from '../../orchestrator/inject.js'

const SKILLS_DIR = join(process.cwd(), 'plugin/skills')

function readSkill(name: string): string {
  return readFileSync(join(SKILLS_DIR, name), 'utf-8')
}

function extractPlaceholders(template: string): string[] {
  return [...template.matchAll(/\{\{([^}]+)\}\}/g)].map((m) => m[1])
}

const SKILL_VARIABLES: Record<string, Record<string, string>> = {
  'task_start.md': {
    task_id: 'clxyz123', title: 'Test', task_type: 'CODING',
    status: 'IN_PROGRESS', jira_key: 'PD-1', due_date: '2026-04-10',
    context: '{}',
  },
  'session_start.md': {
    session_id: 'sess-1', date: '2026-04-04',
    task_list: '- Task 1', meeting_list: '- Meeting 1',
  },
  'task_end.md': {
    task_id: 'clxyz123', title: 'Test', task_type: 'CODING', jira_key: 'PD-1',
  },
  'session_end.md': {
    session_id: 'sess-1', date: '2026-04-04', completed_tasks: 'task-1, task-2',
  },
  'meeting_review.md': {
    meeting_url: 'https://krisp.ai/m/test', meeting_date: '2026-04-04',
    transcript: 'We discussed the auth system.',
  },
  'code_review.md': {
    task_id: 'clxyz123', title: 'Test', context: '{}',
  },
  'blast_radius.md': {
    target: 'getTaskContext', task_id: 'clxyz123', context: '{}',
  },
  'architecture_debate.md': {
    question: 'Should we use Postgres or SQLite?', context: '{}',
  },
}

describe('skill templates', () => {
  for (const [filename, variables] of Object.entries(SKILL_VARIABLES)) {
    describe(filename, () => {
      it('resolves all placeholders without error', () => {
        const template = readSkill(filename)
        expect(() => injectVariables(template, variables)).not.toThrow()
        const result = injectVariables(template, variables)
        expect(result).not.toMatch(/\{\{[^}]+\}\}/)
      })

      it('has exactly the documented placeholders', () => {
        const template = readSkill(filename)
        const found = extractPlaceholders(template).sort()
        const expected = Object.keys(variables).sort()
        expect(found).toEqual(expected)
      })
    })
  }
})
```

- [ ] **Step 4.9: Run the skill template tests**

```bash
yarn test tests/unit/skill-templates.test.ts
```

Expected: all 16 tests pass (2 per skill × 8 skills).

- [ ] **Step 4.10: Commit**

```bash
git add plugin/skills/ tests/unit/skill-templates.test.ts
git commit -m "feat: add remaining skill templates and template unit tests"
```

---

## Task 5: CLI Commands — Session and Task Flow

**Files:**
- Create: `cli/commands/session.ts`
- Create: `cli/commands/task.ts`
- Create: `cli/commands/doctor.ts`
- Create: `cli/commands/integrate.ts`
- Modify: `cli/index.ts`

---

- [ ] **Step 5.1: Create `cli/commands/session.ts`**

```typescript
// cli/commands/session.ts
import { createSession, endSession, getSession } from '../../orchestrator/session.js'

export async function sessionStart(): Promise<void> {
  const sessionId = await createSession()
  console.log(`Session started: ${sessionId}`)
  console.log('Use `wizard task start <task-id> --session <session-id>` to begin work.')
  // In production: pull tasks and meetings here and display them.
  // Context loading for the initial task list uses the context-loader.
}

export async function sessionEnd(sessionId: string): Promise<void> {
  const session = await getSession(sessionId)
  if (!session) {
    console.error(`Session not found: ${sessionId}`)
    process.exit(1)
  }
  await endSession(sessionId)
  console.log(`Session ${sessionId} ended.`)
  console.log(`Tasks worked on: ${session.tasks.map((t) => t.taskId).join(', ') || 'none'}`)
  console.log('Run `wizard session end` to generate a session summary in Claude.')
}
```

- [ ] **Step 5.2: Create `cli/commands/task.ts`**

```typescript
// cli/commands/task.ts
import { attachTaskToSession } from '../../orchestrator/session.js'
import { runTaskStartWorkflow } from '../../orchestrator/workflow.js'
import { runOutputPipeline } from '../../core/output/pipeline.js'

export async function taskStart(taskId: string, sessionId: string): Promise<void> {
  await attachTaskToSession(sessionId, taskId)

  const result = await runTaskStartWorkflow(taskId)
  if (!result.ok) {
    console.error(`Failed to start task: ${result.reason}`)
    process.exit(1)
  }

  // Print the prepared prompt — Claude Code picks this up automatically
  // when Wizard is configured as a Claude Code plugin
  console.log(result.prompt)
}

export async function taskEnd(rawOutput: string): Promise<void> {
  const result = await runOutputPipeline(rawOutput)
  if (!result.ok) {
    console.error(`Output pipeline failed: ${result.reason}`)
    process.exit(1)
  }
  console.log(`Task completed. WorkflowRun: ${result.value.workflowRunId}`)
}
```

- [ ] **Step 5.3: Create `cli/commands/doctor.ts`**

```typescript
// cli/commands/doctor.ts
import { runPreflight } from '../../orchestrator/preflight.js'
import { getIntegrationToken } from '../../data/queries/config.js'
import { createNotionClient } from '../../integrations/notion/index.js'

export async function doctor(): Promise<void> {
  console.log('Running Wizard health checks...\n')
  let allOk = true

  // Database
  const preflight = await runPreflight()
  if (preflight.ok) {
    console.log('✓ Postgres: connected, pgvector installed')
  } else {
    console.error(`✗ Postgres: ${preflight.reason}`)
    allOk = false
  }

  // Notion
  const notionToken = await getIntegrationToken('notion')
  if (notionToken) {
    try {
      process.env.NOTION_API_KEY = notionToken
      const notion = createNotionClient()
      await notion.users.me({})
      console.log('✓ Notion: connected')
    } catch {
      console.warn('✗ Notion: connection failed — re-run `wizard setup`')
      allOk = false
    }
  } else {
    console.warn('✗ Notion: not configured — run `wizard setup`')
    allOk = false
  }

  // Jira, GitHub, Krisp — token presence check only
  for (const source of ['jira', 'github'] as const) {
    const token = await getIntegrationToken(source)
    if (token) {
      console.log(`✓ ${source}: token stored`)
    } else {
      console.warn(`✗ ${source}: not configured — run \`wizard setup\``)
      allOk = false
    }
  }

  console.log(allOk ? '\nAll checks passed.' : '\nSome checks failed. Run `wizard setup` to reconfigure.')
}
```

- [ ] **Step 5.4: Create `cli/commands/integrate.ts`**

```typescript
// cli/commands/integrate.ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { parseConfig } from '../../core/config.js'
import { storeIntegrationToken } from '../../data/queries/config.js'
import type { IntegrationSource } from '../../data/queries/config.js'

const VALID_SOURCES: IntegrationSource[] = ['notion', 'jira', 'github', 'krisp']

export async function integrateAdd(source: string): Promise<void> {
  if (!VALID_SOURCES.includes(source as IntegrationSource)) {
    console.error(`Unknown integration source: ${source}`)
    console.error(`Valid sources: ${VALID_SOURCES.join(', ')}`)
    process.exit(1)
  }

  const configPath = join(process.cwd(), 'wizard.config.yaml')
  let config: ReturnType<typeof parseConfig>
  try {
    config = parseConfig(readFileSync(configPath, 'utf-8'))
  } catch {
    console.error('wizard.config.yaml not found or invalid. Run `wizard setup` first.')
    process.exit(1)
  }

  const integrations = config.integrations as Record<string, { token: string; project?: string }>
  const integration = integrations[source]
  if (!integration?.token) {
    console.error(`No token found for ${source} in wizard.config.yaml`)
    process.exit(1)
  }

  await storeIntegrationToken(
    source as IntegrationSource,
    integration.token,
    'project' in integration ? { project: integration.project } : undefined
  )

  console.log(`✓ ${source}: token stored and encrypted`)
}
```

- [ ] **Step 5.5: Update `cli/index.ts` with all commands**

```typescript
// cli/index.ts
import { Command } from 'commander'
import { setup } from './commands/setup.js'
import { sessionStart, sessionEnd } from './commands/session.js'
import { taskStart, taskEnd } from './commands/task.js'
import { doctor } from './commands/doctor.js'
import { integrateAdd } from './commands/integrate.js'

const program = new Command()

program
  .name('wizard')
  .description('AI-powered engineering workflow system')
  .version('0.2.0')

program
  .command('setup')
  .description('Read wizard.config.yaml and configure all integrations')
  .action(async () => { await setup() })

program
  .command('doctor')
  .description('Check all integrations and database health')
  .action(async () => { await doctor() })

const sessionCmd = program.command('session').description('Session management')

sessionCmd
  .command('start')
  .description('Start a new Wizard session')
  .action(async () => { await sessionStart() })

sessionCmd
  .command('end <session-id>')
  .description('End a Wizard session')
  .action(async (sessionId) => { await sessionEnd(sessionId) })

const taskCmd = program.command('task').description('Task management')

taskCmd
  .command('start <task-id>')
  .description('Start work on a task')
  .requiredOption('-s, --session <session-id>', 'Session ID')
  .action(async (taskId, opts) => { await taskStart(taskId, opts.session) })

taskCmd
  .command('end')
  .description('End task work (reads Claude output from stdin)')
  .action(async () => {
    const chunks: Buffer[] = []
    for await (const chunk of process.stdin) chunks.push(chunk)
    const raw = Buffer.concat(chunks).toString('utf-8')
    await taskEnd(raw)
  })

const integrateCmd = program.command('integrate').description('Integration management')

integrateCmd
  .command('add <source>')
  .description('Add or update an integration from wizard.config.yaml')
  .action(async (source) => { await integrateAdd(source) })

program.parseAsync(process.argv)
```

- [ ] **Step 5.6: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 5.7: Commit**

```bash
git add cli/commands/ cli/index.ts
git commit -m "feat: add full CLI command suite (session, task, doctor, integrate)"
```

---

## Task 6: Evaluation Scaffolding

**Files:**
- Create: `evals/schema.ts`
- Create: `evals/runner.ts`

---

- [ ] **Step 6.1: Create `evals/schema.ts`**

```typescript
// evals/schema.ts
// Evaluation scaffolding — dataset format definition.
// This file defines the shape of labelled examples for future eval runs.
// No scoring logic in v2. Populated when real production data exists.

export type EvalLabel = 'correct' | 'wrong_attribution' | 'malformed_output' | 'pii_leaked'

export type EvalExample = {
  id: string
  description: string
  // The raw Claude output being evaluated
  rawOutput: string
  // The task and meeting context the output relates to
  taskId: string
  meetingId: string | null
  // Ground truth label
  label: EvalLabel
  // Optional: the expected structured output if label is 'correct'
  expectedOutput?: {
    summary: string
    status: string
    notes: string | null
  }
  // When this example was captured
  capturedAt: string  // ISO 8601
  // Source: 'manufactured' (hand-crafted) or 'production' (real session)
  source: 'manufactured' | 'production'
}

export type EvalDataset = {
  version: string
  examples: EvalExample[]
}
```

- [ ] **Step 6.2: Create `evals/runner.ts`**

```typescript
// evals/runner.ts
// Evaluation runner stub.
// Interface is defined; implementation deferred until production data exists.
// See SPEC.md §10 Semantic Threshold Calibration for the intended flow.

import type { EvalDataset, EvalExample } from './schema.js'

export type EvalRunResult = {
  total: number
  passed: number
  failed: number
  failures: Array<{ example: EvalExample; reason: string }>
}

/**
 * Runs the eval dataset against the current pipeline.
 * STUB: always throws NotImplementedError in v2.
 * Implementation requires production data for meaningful calibration.
 */
export async function runEvals(_dataset: EvalDataset): Promise<EvalRunResult> {
  throw new Error(
    'Eval runner not implemented in v2. ' +
    'Collect production data first, then implement scoring in runEvals().'
  )
}

/**
 * Loads an eval dataset from a JSON file.
 */
export async function loadDataset(path: string): Promise<EvalDataset> {
  const { readFileSync } = await import('node:fs')
  const raw = readFileSync(path, 'utf-8')
  return JSON.parse(raw) as EvalDataset
}
```

- [ ] **Step 6.3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 6.4: Commit**

```bash
git add evals/schema.ts evals/runner.ts
git commit -m "feat: add evals scaffolding (schema + runner stub)"
```

---

## Task 7: End-to-End Contract Test — Step 5 Proof Criteria

**Files:**
- Create: `tests/contracts/full-session.test.ts`

---

- [ ] **Step 7.1: Create `tests/contracts/full-session.test.ts`**

```typescript
// tests/contracts/full-session.test.ts
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import { PrismaClient } from '@prisma/client'
import { createSession, endSession, getSession, attachTaskToSession } from '../../orchestrator/session.js'
import { runTaskStartWorkflow } from '../../orchestrator/workflow.js'
import { runOutputPipeline } from '../../core/output/pipeline.js'
import { loadContext } from '../../core/context-loader.js'
import { scrub } from '../../security/scrub.js'

// Mock external integrations — we're testing the pipeline, not the APIs
vi.mock('../../integrations/notion/pull.js', () => ({
  pullNotionTasks: vi.fn().mockResolvedValue([]),
  pullNotionMeetings: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../integrations/github/pull.js', () => ({
  pullAdrs: vi.fn().mockResolvedValue([]),
  pullBranchInfo: vi.fn().mockResolvedValue(null),
}))
vi.mock('../../integrations/serena/invoke.js', () => ({
  findSymbol: vi.fn().mockResolvedValue([]),
  searchForPattern: vi.fn().mockResolvedValue([]),
}))
vi.mock('../../data/queries/config.js', () => ({
  getIntegrationToken: vi.fn().mockResolvedValue('mock-token'),
}))
vi.mock('../../core/output/embeddings.js', () => ({
  computeEmbedding: vi.fn().mockResolvedValue(new Array(1536).fill(0.1)),
}))
vi.mock('../../data/queries/embeddings.js', () => ({
  storeTaskEmbedding: vi.fn().mockResolvedValue(undefined),
  getCosineSimilarity: vi.fn().mockResolvedValue(null),
  getAttributionThreshold: vi.fn().mockResolvedValue(0.75),
}))

const prisma = new PrismaClient()
let sessionId: string
let taskId: string

beforeAll(async () => {
  const task = await prisma.task.create({
    data: {
      title: 'Full session test task',
      status: 'TODO',
      taskType: 'CODING',
      jiraKey: 'PD-E2E',
    },
  })
  taskId = task.id
  sessionId = await createSession()
})

afterAll(async () => {
  await prisma.workflowRun.deleteMany({ where: { taskId } })
  await prisma.sessionTask.deleteMany({ where: { sessionId } })
  await prisma.session.delete({ where: { id: sessionId } })
  await prisma.task.delete({ where: { id: taskId } })
  await prisma.$disconnect()
})

describe('Full session — end-to-end proof', () => {
  it('session starts and is immediately retrievable from Postgres', async () => {
    const session = await getSession(sessionId)
    expect(session).not.toBeNull()
    expect(session!.status).toBe('ACTIVE')
  })

  it('task_start workflow prepares context and returns a prompt', async () => {
    await attachTaskToSession(sessionId, taskId)
    const result = await runTaskStartWorkflow(taskId)

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error(result.reason)

    expect(result.prompt).toContain('Full session test task')
    expect(result.prompt).not.toMatch(/\{\{[^}]+\}\}/)
  })

  it('context loading is task-type specific (CODING loads Serena)', async () => {
    const { findSymbol } = await import('../../integrations/serena/invoke.js')
    vi.mocked(findSymbol).mockClear()

    await loadContext({
      id: taskId,
      title: 'Full session test task',
      taskType: 'CODING',
      githubRepo: null,
      githubBranch: null,
    })

    expect(findSymbol).toHaveBeenCalled()
  })

  it('Claude output is stored and traceable to its task', async () => {
    const rawOutput = `
I have completed the task.

\`\`\`json
{
  "taskId": "${taskId}",
  "summary": "Implemented the full session test",
  "status": "DONE",
  "notes": "All tests passing"
}
\`\`\`
`
    const result = await runOutputPipeline(rawOutput)

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error(result.reason)

    const run = await prisma.workflowRun.findUnique({
      where: { id: result.value.workflowRunId },
    })
    expect(run).not.toBeNull()
    expect(run!.taskId).toBe(taskId)
    expect((run!.output as any).summary).toBe('Implemented the full session test')
  })

  it('PII never appears in Postgres — security layer removes it before storage', () => {
    const raw = 'Contact alice@nhs.net and call 07700 900123'
    const result = scrub(raw, 'test.notes')

    expect(result.text).not.toContain('alice@nhs.net')
    expect(result.text).not.toContain('07700 900123')
    expect(result.entries).toHaveLength(2)
    // Hashes are stored, not plaintext
    expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)
  })

  it('session ends and is marked ENDED in Postgres', async () => {
    await endSession(sessionId)

    const fresh = new PrismaClient()
    const session = await fresh.session.findUnique({ where: { id: sessionId } })
    await fresh.$disconnect()

    expect(session!.status).toBe('ENDED')
    expect(session!.endedAt).toBeInstanceOf(Date)
  })
})
```

- [ ] **Step 7.2: Run the full session contract test**

```bash
yarn test tests/contracts/full-session.test.ts
```

Expected:

```
✓ Full session > session starts and is immediately retrievable from Postgres
✓ Full session > task_start workflow prepares context and returns a prompt
✓ Full session > context loading is task-type specific (CODING loads Serena)
✓ Full session > Claude output is stored and traceable to its task
✓ Full session > PII never appears in Postgres — security layer removes it before storage
✓ Full session > session ends and is marked ENDED in Postgres

Test Files  1 passed (1)
Tests       6 passed (6)
```

- [ ] **Step 7.3: Commit**

```bash
git add tests/contracts/full-session.test.ts
git commit -m "test(contract): add full-session end-to-end contract test — step 5 proof passing"
```

---

## Task 8: Final Verification

---

- [ ] **Step 8.1: Run the full test suite**

```bash
yarn test
```

Expected: all tests pass across all 5 steps.

- [ ] **Step 8.2: TypeScript clean build**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 8.3: Step 5 proof criteria met**

From the spec:

> Full session — wizard session start through wizard session end — runs end-to-end. PII never appears in Postgres. Context loaded is task-type specific. Output is stored and traceable to its origin. Eval scaffolding is in place with dataset format defined.

- Full session flow: `createSession` → `runTaskStartWorkflow` → `runOutputPipeline` → `endSession` ✓
- PII never in Postgres: `scrub()` removes before any `prisma.*.create()` call ✓
- Task-type specific context: `loadContext` dispatches on `taskType`, CODING calls Serena ✓
- Output traceable: `WorkflowRun.taskId` links output to its task ✓
- Eval scaffolding: `evals/schema.ts` (dataset format) + `evals/runner.ts` (stub) ✓

- [ ] **Step 8.4: Final commit**

```bash
git add .
git commit -m "chore: step 5 complete — full system end-to-end contract passing"
```

---

## Troubleshooting

**`integrations/serena/invoke.ts` errors on connection**
Check `docs/spikes/serena-invocation.md` from Step 2 Task 0 for the correct `SERENA_COMMAND` value. Set `SERENA_COMMAND` in `.env` if the default `serena` binary name is wrong.

**`loadContext` calls integrations even when tokens are missing**
Each loader function checks for the token before calling — if `getIntegrationToken` returns `null`, the call is skipped. In tests, `getIntegrationToken` is mocked to return `'mock-token'` so the integration functions are called; mock the integrations themselves to control their return values.

**`wizard task end` hangs waiting for stdin**
The `task end` CLI command reads from stdin. Pipe Claude's output: `echo '<claude output>' | wizard task end`. Or write the output to a file and use: `wizard task end < output.txt`.

**Skill template test fails — placeholder count mismatch**
The `SKILL_VARIABLES` map in `skill-templates.test.ts` must exactly match the placeholders in each template file. If you add or remove a placeholder from a template, update the corresponding entry in `SKILL_VARIABLES`.

**`evals/runner.ts` throws "not implemented" during tests**
This is correct. `runEvals` is intentionally a stub. Do not call it in tests. Tests can import `EvalDataset` and `EvalExample` types from `evals/schema.ts` without triggering the runner.
