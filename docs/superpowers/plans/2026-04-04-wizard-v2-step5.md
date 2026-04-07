# Wizard v2 Step 5 — Full System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build remaining integrations (Jira, Krisp, GitHub), task-type aware context loading, CodeChunkEmbedding with chunking strategy, the full session flow (`wizard session start` → `wizard session end`), remaining CLI commands, remaining skill templates in `llm/prompts/`, `llm/packaging/` rendering into model-specific install formats, and evaluation scaffolding in `evals/`. Prove the full session runs end-to-end with PII-free Postgres, task-type specific context, and traceable output.

**Architecture:** This step completes the system. Each integration follows the same pattern as Notion: pull raw data → route through security → return scrubbed results. Jira maps to `externalTaskId` (not `jiraKey`). GitHub creates/updates `Repo` records and links via `repoId` FK. Krisp creates `Meeting` + `ActionItem` records (not `String[]` actionItems). The `core/context-loader.ts` switches on task type to call only the relevant integrations, using new models (Repo, Note, ActionItem) for context assembly. CLI commands orchestrate the full session flow by calling the MCP tools and orchestrator functions. Skill templates complete the `llm/prompts/` directory. `llm/packaging/` renders templates into model-specific installation formats. `evals/` is scaffolding only — types and a runner stub; no scoring logic. All IDs are `Int @id @default(autoincrement())`. All imports from the generated Prisma client use `../../generated/prisma/index.js`, not `@prisma/client`.

**Tech Stack:** TypeScript (ESM, bundler), Prisma (`prisma-client` generator, `output = "../generated/prisma"`), Vitest, `commander`, existing `@notionhq/client`. New: GitHub REST via `@octokit/rest`, `@langchain/textsplitters` for code chunking, Jira via direct REST (no heavy SDK), Krisp via file/MCP read. No `openai` dependency — embeddings use nomic-embed-text via Ollama (`vector(768)`).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `integrations/jira/pull.ts` | Pull task details from Jira REST API; maps to `externalTaskId` |
| Create | `integrations/krisp/pull.ts` | Read Krisp meeting transcripts; creates Meeting + ActionItem records |
| Create | `integrations/github/pull.ts` | Read ADRs and branch info from GitHub; creates/updates Repo records, links via `repoId` FK |
| Create | `core/context-loader.ts` | Task-type aware context loading — dispatches to correct integrations, uses Repo, Note, ActionItem models |
| Create | `services/code-chunker.ts` | Chunks code files using @langchain/textsplitters RecursiveCharacterTextSplitter (512 tokens, 256 overlap) |
| Create | `interfaces/cli/commands/session.ts` | `wizard session start` / `wizard session end` |
| Create | `interfaces/cli/commands/task.ts` | `wizard task start` / `wizard task end` |
| Create | `interfaces/cli/commands/doctor.ts` | `wizard doctor` — health check all integrations + DB |
| Create | `interfaces/cli/commands/integrate.ts` | `wizard integrate add <source>` |
| Modify | `interfaces/cli/index.ts` | Register all new commands |
| Create | `llm/prompts/session_start.md` | Skill template |
| Create | `llm/prompts/task_end.md` | Skill template |
| Create | `llm/prompts/session_end.md` | Skill template |
| Create | `llm/prompts/meeting_review.md` | Skill template — outputs ActionItem array, not String[] |
| Create | `llm/prompts/code_review.md` | Skill template |
| Create | `llm/prompts/blast_radius.md` | Skill template |
| Create | `llm/prompts/architecture_debate.md` | Skill template |
| Create | `llm/packaging/render.ts` | Renders prompt templates into model-specific install formats |
| Create | `llm/packaging/targets/claude.ts` | Claude-specific packaging (`.claude-plugin/`) |
| Create | `llm/packaging/targets/ollama.ts` | Ollama-specific packaging (modelfile prompt injection) |
| Create | `evals/schema.ts` | Dataset format type definitions |
| Create | `evals/runner.ts` | Runner stub — interface defined, body deferred |
| Modify | `package.json` | Add `@octokit/rest`, `@langchain/textsplitters` |
| Modify | `tsconfig.json` | Add `evals/**/*.ts` to `include` |
| Create | `tests/unit/context-loader.test.ts` | Each task type returns correct source set |
| Create | `tests/unit/code-chunker.test.ts` | Chunking produces correct chunkIndex, contentHash |
| Create | `tests/unit/skill-templates.test.ts` | All remaining templates resolve correctly |
| Create | `tests/unit/packaging.test.ts` | Packaging renders templates without unresolved placeholders |
| Create | `tests/contracts/full-session.test.ts` | End-to-end session proof criteria |

---

## Task 1: Dependencies + Directory Structure

**Files:**
- Modify: `package.json`
- Modify: `tsconfig.json`

---

- [ ] **Step 1.1: Install new dependencies**

```bash
yarn add @octokit/rest @langchain/textsplitters
```

- [ ] **Step 1.2: Update `package.json`**

Add `@octokit/rest` and `@langchain/textsplitters` to `dependencies`. Note: Prisma generator is `"prisma-client"` with `output = "../generated/prisma"`. No `@prisma/client` runtime import — use `../../generated/prisma/index.js`.

```json
{
  "name": "wizard",
  "packageManager": "yarn@4.12.0",
  "type": "module",
  "bin": {
    "wizard-mcp": "./build/mcp/index.js",
    "wizard": "./build/interfaces/cli/index.js"
  },
  "prisma": {
    "schema": "data/prisma/schema.prisma"
  },
  "dependencies": {
    "@langchain/textsplitters": "^0.1.0",
    "@modelcontextprotocol/sdk": "^1.28.0",
    "@notionhq/client": "^5.15.0",
    "@octokit/rest": "^21.0.0",
    "commander": "^12.0.0",
    "js-yaml": "^4.1.0",
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
    "build": "tsc && chmod 755 build/mcp/index.js && chmod 755 build/interfaces/cli/index.js",
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
    "core/**/*.ts",
    "security/**/*.ts",
    "llm/**/*.ts",
    "services/**/*.ts",
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
mkdir -p integrations/jira integrations/krisp integrations/github evals llm/prompts llm/adapters llm/packaging/targets services
```

- [ ] **Step 1.5: Commit**

```bash
git add package.json tsconfig.json
git commit -m "chore: add octokit and textsplitters deps, evals/ to tsconfig for step 5"
```

---

## Task 2: Remaining Integrations

**Files:**
- Create: `integrations/jira/pull.ts`
- Create: `integrations/krisp/pull.ts`
- Create: `integrations/github/pull.ts`

---

- [ ] **Step 2.1: Create `integrations/jira/pull.ts`**

Jira is called via REST. No heavy SDK — `fetch` is sufficient for a single endpoint. Maps to `externalTaskId` (not `jiraKey`). Creates Task records with `externalTaskId` field, `TaskPriority` enum (not `Priority`), and `TaskStatus` that includes `BLOCKED`.

```typescript
// integrations/jira/pull.ts
import { scrub } from '../../security/scrub.js'
import type { ScrubResult } from '../../security/types.js'

export type RawJiraTask = {
  externalTaskId: string
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
 * Returns externalTaskId (the Jira key, e.g. "PD-42") for FK mapping.
 *
 * Downstream: the service layer maps this to a Task record:
 *   - externalTaskId = data.key (e.g. "PD-42")
 *   - priority uses TaskPriority enum (LOW | MEDIUM | HIGH)
 *   - status uses TaskStatus enum (TODO | IN_PROGRESS | DONE | BLOCKED)
 *   - Task.id is Int @id @default(autoincrement())
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
    externalTaskId: data.key,
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

Krisp transcripts arrive as text files or via MCP. In v2, Krisp's MCP method reads transcripts as plain text. The transcript is scrubbed before being returned. Downstream, the service layer creates a `Meeting` record and separate `ActionItem` records (not `String[]` actionItems).

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
 *
 * Downstream: the service layer creates:
 *   - Meeting record (Int ID, title, outline, keyPoints, krispUrl)
 *   - ActionItem records (separate model, FK to Meeting via meetingId)
 *   - NOT String[] actionItems — ActionItem is its own table
 *   - Meeting.id is Int @id @default(autoincrement())
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

GitHub pull creates/updates `Repo` records (Int ID, name, url, platform: `RepoProvider`) and links via `repoId` FK. Branch info resolves to the Repo model, not raw `githubBranch`/`githubRepo` fields.

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

export type RawRepoInfo = {
  name: string
  url: string
  platform: 'GITHUB'
}

export type BranchInfo = {
  name: string
  lastCommitSha: string
  lastCommitMessage: ScrubResult
  repo: RawRepoInfo
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
 * Returns RawRepoInfo for upserting the Repo model (Int ID, repoId FK).
 *
 * Downstream: the service/repository layer:
 *   - Upserts a Repo record (unique on url) with platform = GITHUB
 *   - Links the Task to this Repo via repoId FK (Int)
 *   - Sets Task.branch = branch name
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
      repo: {
        name: repo,
        url: `https://github.com/${owner}/${repo}`,
        platform: 'GITHUB',
      },
    }
  } catch {
    return null
  }
}
```

- [ ] **Step 2.4: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 2.5: Commit**

```bash
git add integrations/jira/pull.ts integrations/krisp/pull.ts integrations/github/pull.ts
git commit -m "feat: add Jira, Krisp, and GitHub integrations"
```

---

## Task 3: `core/context-loader.ts` — Task-Type Aware Context Loading

**Files:**
- Create: `core/context-loader.ts`
- Create: `tests/unit/context-loader.test.ts`

Context loader uses new models (Repo, Note, ActionItem) and resolves `repoId` FK (Int) for GitHub context. All entity IDs are integers.

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
vi.mock('../../data/repositories/config.js', () => ({
  getIntegrationToken: vi.fn().mockResolvedValue('mock-token'),
}))

import { loadContext } from '../../core/context-loader.js'
import { pullNotionTasks, pullNotionMeetings } from '../../integrations/notion/pull.js'
import { pullAdrs, pullBranchInfo } from '../../integrations/github/pull.js'

const baseTask = {
  id: 1,
  title: 'Test task',
  taskType: 'CODING' as const,
  repoId: 1,
  branch: 'feat/auth',
  externalTaskId: 'PD-42',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('loadContext', () => {
  it('CODING task loads Notion tasks, ADRs, and branch info', async () => {
    await loadContext({ ...baseTask, taskType: 'CODING' })

    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullAdrs).toHaveBeenCalled()
    expect(pullBranchInfo).toHaveBeenCalled()
  })

  it('MEETING_REVIEW task loads only Krisp — no Notion, no GitHub', async () => {
    await loadContext({ ...baseTask, taskType: 'MEETING_REVIEW' })

    expect(pullNotionTasks).not.toHaveBeenCalled()
    expect(pullAdrs).not.toHaveBeenCalled()
  })

  it('DEBUGGING task loads Notion tasks — does not load ADRs', async () => {
    await loadContext({ ...baseTask, taskType: 'DEBUGGING' })

    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullAdrs).not.toHaveBeenCalled()
  })

  it('ADR task loads GitHub ADRs and Notion', async () => {
    await loadContext({ ...baseTask, taskType: 'ADR' })

    expect(pullAdrs).toHaveBeenCalled()
    expect(pullNotionMeetings).toHaveBeenCalled()
  })

  it('INVESTIGATION task loads all sources', async () => {
    await loadContext({ ...baseTask, taskType: 'INVESTIGATION' })

    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullNotionMeetings).toHaveBeenCalled()
    expect(pullAdrs).toHaveBeenCalled()
  })

  it('TEST_GENERATION task loads Notion tasks — not ADRs', async () => {
    await loadContext({ ...baseTask, taskType: 'TEST_GENERATION' })

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
// Task-type dispatch table — from SPEC_v8 §6 Session Architecture
//
// Task Type       | Sources
// --------------- | -----------------------------------------
// CODING          | Notion tasks, GitHub ADRs, branch info
// DEBUGGING       | Notion tasks
// INVESTIGATION   | Notion tasks, Notion meetings, GitHub ADRs
// ADR             | GitHub ADRs, Notion meetings
// TEST_GENERATION | Notion tasks
// MEETING_REVIEW  | Krisp only (no external calls here — Krisp is read at CLI level)

import { pullNotionTasks, pullNotionMeetings } from '../integrations/notion/pull.js'
import { pullAdrs, pullBranchInfo } from '../integrations/github/pull.js'
import { getIntegrationToken } from '../data/repositories/config.js'
import type { TaskType } from '../shared/types.js'

export type ContextInput = {
  id: number
  title: string
  taskType: TaskType
  repoId?: number | null
  branch?: string | null
  externalTaskId?: string | null
}

export type LoadedContext = {
  notionTasks: unknown[]
  notionMeetings: unknown[]
  adrs: unknown[]
  branchInfo: unknown | null
}

/**
 * Loads context appropriate for the task type.
 * Only calls the sources the task type actually needs — no unnecessary tokens.
 * Uses repoId FK (Int) for Repo lookups and externalTaskId for Jira mapping.
 * All entity IDs are integers (Int @id @default(autoincrement())).
 */
export async function loadContext(task: ContextInput): Promise<LoadedContext> {
  const notionToken = await getIntegrationToken('notion')
  const githubToken = await getIntegrationToken('github')

  // Notion database IDs come from IntegrationConfig metadata in production.
  // Using env vars as fallback for now.
  const notionTasksDb = process.env.NOTION_TASKS_DB_ID ?? ''
  const notionMeetingsDb = process.env.NOTION_MEETINGS_DB_ID ?? ''
  const githubOwner = process.env.GITHUB_OWNER ?? ''
  // Repo name resolved from repoId FK in production; env var fallback
  const githubRepo = process.env.GITHUB_REPO ?? ''

  const ctx: LoadedContext = {
    notionTasks: [],
    notionMeetings: [],
    adrs: [],
    branchInfo: null,
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
    if (githubToken && githubOwner && githubRepo) {
      ctx.adrs = await pullAdrs(githubToken, githubOwner, githubRepo)
    }
  }
  const loadBranchInfo = async () => {
    if (githubToken && githubOwner && githubRepo && task.branch) {
      ctx.branchInfo = await pullBranchInfo(
        githubToken, githubOwner, githubRepo, task.branch
      )
    }
  }

  switch (task.taskType) {
    case 'CODING':
      await Promise.all([loadNotionTasks(), loadAdrs(), loadBranchInfo()])
      break
    case 'DEBUGGING':
      await Promise.all([loadNotionTasks()])
      break
    case 'INVESTIGATION':
      await Promise.all([loadNotionTasks(), loadNotionMeetings(), loadAdrs()])
      break
    case 'ADR':
      await Promise.all([loadAdrs(), loadNotionMeetings()])
      break
    case 'TEST_GENERATION':
      await Promise.all([loadNotionTasks()])
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
✓ loadContext > CODING task loads Notion tasks, ADRs, and branch info
✓ loadContext > MEETING_REVIEW task loads only Krisp — no Notion, no GitHub
✓ loadContext > DEBUGGING task loads Notion tasks — does not load ADRs
✓ loadContext > ADR task loads GitHub ADRs and Notion
✓ loadContext > INVESTIGATION task loads all sources
✓ loadContext > TEST_GENERATION task loads Notion tasks — not ADRs

Test Files  1 passed (1)
Tests       6 passed (6)
```

- [ ] **Step 3.5: Commit**

```bash
git add core/context-loader.ts tests/unit/context-loader.test.ts
git commit -m "feat: add task-type aware context loading to core/context-loader"
```

---

## Task 4: Remaining Skill Templates + Packaging

**Files:**
- Create: `llm/prompts/session_start.md`
- Create: `llm/prompts/task_end.md`
- Create: `llm/prompts/session_end.md`
- Create: `llm/prompts/meeting_review.md`
- Create: `llm/prompts/code_review.md`
- Create: `llm/prompts/blast_radius.md`
- Create: `llm/prompts/architecture_debate.md`
- Create: `llm/packaging/render.ts`
- Create: `llm/packaging/targets/claude.ts`
- Create: `llm/packaging/targets/ollama.ts`
- Create: `tests/unit/skill-templates.test.ts`
- Create: `tests/unit/packaging.test.ts`

---

- [ ] **Step 4.1: Create `llm/prompts/session_start.md`**

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

Variables: `session_id` (Int), `date`, `task_list`, `meeting_list`

- [ ] **Step 4.2: Create `llm/prompts/task_end.md`**

```markdown
The work on the following task is complete.

Task: {{title}} ({{task_id}})
Type: {{task_type}}
External Task ID: {{external_task_id}}

Produce a structured summary of what was done. Reply with ONLY the following JSON block and nothing else:

```json
{
  "taskId": {{task_id}},
  "summary": "<one paragraph summary of what was done>",
  "status": "<TODO|IN_PROGRESS|DONE|BLOCKED>",
  "meetingId": <meeting ID (int) if this work relates to a meeting, otherwise null>,
  "externalTaskId": "{{external_task_id}}",
  "notes": "<any implementation notes or decisions made>"
}
```
```

Variables: `task_id` (Int), `title`, `task_type`, `external_task_id`

- [ ] **Step 4.3: Create `llm/prompts/session_end.md`**

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

Variables: `session_id` (Int), `date`, `completed_tasks`

- [ ] **Step 4.4: Create `llm/prompts/meeting_review.md`**

Outputs `ActionItem` array — each item becomes a separate `ActionItem` record (not `String[]`).

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
  "actionItems": [{"action": "<action description>", "dueDate": "<ISO date or null>"}]
}
```
```

Variables: `meeting_url`, `meeting_date`, `transcript`

Note: Each object in `actionItems` maps to a separate `ActionItem` model record with its own `Int` ID, `meetingId` FK, and optional `taskId` FK (set when the action item graduates into a Task).

- [ ] **Step 4.5: Create `llm/prompts/code_review.md`**

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

Variables: `task_id` (Int), `title`, `context`

- [ ] **Step 4.6: Create `llm/prompts/blast_radius.md`**

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

Variables: `target`, `task_id` (Int), `context`

- [ ] **Step 4.7: Create `llm/prompts/architecture_debate.md`**

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

- [ ] **Step 4.8: Create `llm/packaging/render.ts`**

Renders prompt templates from `llm/prompts/` into model-specific installation formats. Each target adapter defines how to transform a resolved template into the format the model expects.

```typescript
// llm/packaging/render.ts
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { join, basename } from 'node:path'
import type { PackagingTarget } from './targets/types.js'

export type RenderOptions = {
  promptsDir: string
  outputDir: string
  target: PackagingTarget
}

/**
 * Renders all prompt templates from promptsDir into the target-specific
 * installation format and writes them to outputDir.
 *
 * This is the bridge between model-agnostic templates (llm/prompts/)
 * and model-specific installation (e.g. .claude-plugin/, Ollama modelfile).
 */
export function renderAll(options: RenderOptions): string[] {
  const { promptsDir, outputDir, target } = options
  const { readdirSync } = require('node:fs') as typeof import('node:fs')
  const files = readdirSync(promptsDir).filter((f: string) => f.endsWith('.md'))

  mkdirSync(outputDir, { recursive: true })

  const rendered: string[] = []
  for (const file of files) {
    const template = readFileSync(join(promptsDir, file), 'utf-8')
    const output = target.render(basename(file, '.md'), template)
    const outputPath = join(outputDir, target.outputFilename(basename(file, '.md')))
    writeFileSync(outputPath, output, 'utf-8')
    rendered.push(outputPath)
  }

  return rendered
}
```

- [ ] **Step 4.9: Create `llm/packaging/targets/types.ts`**

```typescript
// llm/packaging/targets/types.ts
export interface PackagingTarget {
  name: string
  /** Renders a prompt template into the target-specific format */
  render(skillName: string, template: string): string
  /** Returns the output filename for the rendered skill */
  outputFilename(skillName: string): string
}
```

- [ ] **Step 4.10: Create `llm/packaging/targets/claude.ts`**

```typescript
// llm/packaging/targets/claude.ts
import type { PackagingTarget } from './types.js'

export const claudeTarget: PackagingTarget = {
  name: 'claude',

  render(skillName: string, template: string): string {
    return JSON.stringify({
      name: skillName,
      description: `Wizard skill: ${skillName}`,
      prompt: template,
    }, null, 2)
  },

  outputFilename(skillName: string): string {
    return `${skillName}.json`
  },
}
```

- [ ] **Step 4.11: Create `llm/packaging/targets/ollama.ts`**

```typescript
// llm/packaging/targets/ollama.ts
import type { PackagingTarget } from './types.js'

export const ollamaTarget: PackagingTarget = {
  name: 'ollama',

  render(skillName: string, template: string): string {
    // Ollama modelfile format — SYSTEM directive with the skill prompt
    return `# Wizard skill: ${skillName}\nFROM wizard-base\nSYSTEM """${template}"""\n`
  },

  outputFilename(skillName: string): string {
    return `Modelfile.${skillName}`
  },
}
```

- [ ] **Step 4.12: Write the skill templates unit test**

```typescript
// tests/unit/skill-templates.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { injectVariables } from '../../orchestrator/inject.js'

const SKILLS_DIR = join(process.cwd(), 'llm/prompts')

function readSkill(name: string): string {
  return readFileSync(join(SKILLS_DIR, name), 'utf-8')
}

function extractPlaceholders(template: string): string[] {
  return [...template.matchAll(/\{\{([^}]+)\}\}/g)].map((m) => m[1])
}

const SKILL_VARIABLES: Record<string, Record<string, string>> = {
  'task_start.md': {
    task_id: '42', title: 'Test', task_type: 'CODING',
    status: 'IN_PROGRESS', external_task_id: 'PD-1', due_date: '2026-04-10',
    context: '{}',
  },
  'session_start.md': {
    session_id: '1', date: '2026-04-04',
    task_list: '- Task 1', meeting_list: '- Meeting 1',
  },
  'task_end.md': {
    task_id: '42', title: 'Test', task_type: 'CODING', external_task_id: 'PD-1',
  },
  'session_end.md': {
    session_id: '1', date: '2026-04-04', completed_tasks: 'task-1, task-2',
  },
  'meeting_review.md': {
    meeting_url: 'https://krisp.ai/m/test', meeting_date: '2026-04-04',
    transcript: 'We discussed the auth system.',
  },
  'code_review.md': {
    task_id: '42', title: 'Test', context: '{}',
  },
  'blast_radius.md': {
    target: 'getTaskContext', task_id: '42', context: '{}',
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

- [ ] **Step 4.13: Write the packaging unit test**

```typescript
// tests/unit/packaging.test.ts
import { describe, it, expect } from 'vitest'
import { claudeTarget } from '../../llm/packaging/targets/claude.js'
import { ollamaTarget } from '../../llm/packaging/targets/ollama.js'

const SAMPLE_TEMPLATE = 'You are a wizard. Task: {{task_id}}'

describe('packaging targets', () => {
  describe('claude target', () => {
    it('renders to JSON with prompt field', () => {
      const output = claudeTarget.render('task_start', SAMPLE_TEMPLATE)
      const parsed = JSON.parse(output)
      expect(parsed.name).toBe('task_start')
      expect(parsed.prompt).toBe(SAMPLE_TEMPLATE)
    })

    it('produces .json output filename', () => {
      expect(claudeTarget.outputFilename('task_start')).toBe('task_start.json')
    })
  })

  describe('ollama target', () => {
    it('renders to Modelfile format with SYSTEM directive', () => {
      const output = ollamaTarget.render('task_start', SAMPLE_TEMPLATE)
      expect(output).toContain('SYSTEM')
      expect(output).toContain(SAMPLE_TEMPLATE)
      expect(output).toContain('FROM wizard-base')
    })

    it('produces Modelfile.<skill> output filename', () => {
      expect(ollamaTarget.outputFilename('task_start')).toBe('Modelfile.task_start')
    })
  })
})
```

- [ ] **Step 4.14: Run the skill template and packaging tests**

```bash
yarn test tests/unit/skill-templates.test.ts tests/unit/packaging.test.ts
```

Expected: all 16 skill template tests pass (2 per skill x 8 skills), plus 4 packaging tests pass.

- [ ] **Step 4.15: Commit**

```bash
git add llm/prompts/ llm/packaging/ tests/unit/skill-templates.test.ts tests/unit/packaging.test.ts
git commit -m "feat: add remaining skill templates, packaging layer, and unit tests"
```

---

## Task 5: CLI Commands — Session and Task Flow

**Files:**
- Create: `interfaces/cli/commands/session.ts`
- Create: `interfaces/cli/commands/task.ts`
- Create: `interfaces/cli/commands/doctor.ts`
- Create: `interfaces/cli/commands/integrate.ts`
- Modify: `interfaces/cli/index.ts`

Session flow uses int IDs throughout. All entity references are `Int @id @default(autoincrement())`.

---

- [ ] **Step 5.1: Create `interfaces/cli/commands/session.ts`**

```typescript
// interfaces/cli/commands/session.ts
import { createSession, endSession, getSession } from '../../orchestrator/session.js'

export async function sessionStart(): Promise<void> {
  const sessionId = await createSession()
  console.log(`Session started: ${sessionId}`)
  console.log('Use `wizard task start <task-id> --session <session-id>` to begin work.')
  // In production: pull tasks and meetings here and display them.
  // Context loading for the initial task list uses the context-loader.
}

export async function sessionEnd(sessionId: string): Promise<void> {
  const id = parseInt(sessionId, 10)
  if (isNaN(id)) {
    console.error(`Invalid session ID: ${sessionId} — must be an integer`)
    process.exit(1)
  }

  const session = await getSession(id)
  if (!session) {
    console.error(`Session not found: ${id}`)
    process.exit(1)
  }
  await endSession(id)
  console.log(`Session ${id} ended.`)
  console.log(`Tasks worked on: ${session.tasks.map((t) => t.taskId).join(', ') || 'none'}`)
  console.log('Run `wizard session end` to generate a session summary via the LLM layer.')
}
```

- [ ] **Step 5.2: Create `interfaces/cli/commands/task.ts`**

```typescript
// interfaces/cli/commands/task.ts
import { attachTaskToSession } from '../../orchestrator/session.js'
import { runTaskStartWorkflow } from '../../orchestrator/workflow.js'
import { runOutputPipeline } from '../../core/output/pipeline.js'

export async function taskStart(taskIdStr: string, sessionIdStr: string): Promise<void> {
  const taskId = parseInt(taskIdStr, 10)
  const sessionId = parseInt(sessionIdStr, 10)

  if (isNaN(taskId) || isNaN(sessionId)) {
    console.error('Task ID and session ID must be integers')
    process.exit(1)
  }

  await attachTaskToSession(sessionId, taskId)

  const result = await runTaskStartWorkflow(taskId)
  if (!result.ok) {
    console.error(`Failed to start task: ${result.reason}`)
    process.exit(1)
  }

  // Print the prepared prompt — the LLM adapter picks this up
  // when Wizard is configured as a plugin
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

- [ ] **Step 5.3: Create `interfaces/cli/commands/doctor.ts`**

```typescript
// interfaces/cli/commands/doctor.ts
import { runPreflight } from '../../orchestrator/preflight.js'
import { getIntegrationToken } from '../../data/repositories/config.js'
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

  // Jira, GitHub — token presence check only
  for (const source of ['jira', 'github'] as const) {
    const token = await getIntegrationToken(source)
    if (token) {
      console.log(`✓ ${source}: token stored`)
    } else {
      console.warn(`✗ ${source}: not configured — run \`wizard setup\``)
      allOk = false
    }
  }

  // Ollama — embedding model check (nomic-embed-text, vector(768))
  try {
    const response = await fetch('http://localhost:11434/api/tags')
    if (response.ok) {
      const data = await response.json() as { models: Array<{ name: string }> }
      const hasNomic = data.models?.some((m) => m.name.includes('nomic-embed-text'))
      if (hasNomic) {
        console.log('✓ Ollama: nomic-embed-text available (vector(768))')
      } else {
        console.warn('✗ Ollama: nomic-embed-text not found — run `ollama pull nomic-embed-text`')
        allOk = false
      }
    }
  } catch {
    console.warn('✗ Ollama: not running — start with `ollama serve`')
    allOk = false
  }

  console.log(allOk ? '\nAll checks passed.' : '\nSome checks failed. Run `wizard setup` to reconfigure.')
}
```

- [ ] **Step 5.4: Create `interfaces/cli/commands/integrate.ts`**

```typescript
// interfaces/cli/commands/integrate.ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { parseConfig } from '../../core/config.js'
import { storeIntegrationToken } from '../../data/repositories/config.js'
import type { IntegrationSource } from '../../data/repositories/config.js'

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

- [ ] **Step 5.5: Update `interfaces/cli/index.ts` with all commands**

```typescript
// interfaces/cli/index.ts
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
  .description('End task work (reads LLM output from stdin)')
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
git add interfaces/cli/commands/ interfaces/cli/index.ts
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
// All entity IDs are Int (autoincrement), matching the Prisma schema.

export type EvalLabel = 'correct' | 'wrong_attribution' | 'malformed_output' | 'pii_leaked'

export type EvalExample = {
  id: number
  description: string
  // The raw LLM output being evaluated
  rawOutput: string
  // The task and meeting context the output relates to (int IDs)
  taskId: number
  meetingId: number | null
  // Ground truth label
  label: EvalLabel
  // Optional: the expected structured output if label is 'correct'
  expectedOutput?: {
    summary: string
    status: string
    externalTaskId: string | null
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
// See SPEC_v6.md §12 Semantic Threshold Calibration for the intended flow.
// Embeddings use nomic-embed-text via Ollama (vector(768)), not OpenAI.

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

All IDs are integers. Import from `../../generated/prisma/index.js`, not `@prisma/client`. Uses `externalTaskId`, `TaskPriority`, `TaskStatus` (including `BLOCKED`), `ActionItem` model, and `Repo` model.

```typescript
// tests/contracts/full-session.test.ts
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import { PrismaClient } from '../../generated/prisma/index.js'
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
vi.mock('../../data/repositories/config.js', () => ({
  getIntegrationToken: vi.fn().mockResolvedValue('mock-token'),
}))
vi.mock('../../core/output/embeddings.js', () => ({
  computeEmbedding: vi.fn().mockResolvedValue(new Array(768).fill(0.1)),
}))
vi.mock('../../data/repositories/embeddings.js', () => ({
  storeTaskEmbedding: vi.fn().mockResolvedValue(undefined),
  getCosineSimilarity: vi.fn().mockResolvedValue(null),
  getAttributionThreshold: vi.fn().mockResolvedValue(0.75),
}))

const prisma = new PrismaClient()
let sessionId: number
let taskId: number

beforeAll(async () => {
  const task = await prisma.task.create({
    data: {
      title: 'Full session test task',
      status: 'TODO',
      taskType: 'CODING',
      externalTaskId: 'PD-E2E',
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

  it('context loading is task-type specific (CODING loads Notion tasks and ADRs)', async () => {
    const { pullNotionTasks } = await import('../../integrations/notion/pull.js')
    const { pullAdrs } = await import('../../integrations/github/pull.js')
    vi.mocked(pullNotionTasks).mockClear()
    vi.mocked(pullAdrs).mockClear()

    await loadContext({
      id: taskId,
      title: 'Full session test task',
      taskType: 'CODING',
      repoId: null,
      branch: null,
    })

    expect(pullNotionTasks).toHaveBeenCalled()
    expect(pullAdrs).toHaveBeenCalled()
  })

  it('LLM output is stored and traceable to its task', async () => {
    const rawOutput = `
I have completed the task.

\`\`\`json
{
  "taskId": ${taskId},
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
✓ Full session > context loading is task-type specific (CODING loads Notion tasks and ADRs)
✓ Full session > LLM output is stored and traceable to its task
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

From SPEC_v8:

> Full session — wizard session start through wizard session end — runs end-to-end. PII never appears in Postgres. Context loaded is task-type specific. Output is stored and traceable to its origin. Eval scaffolding is in place with dataset format defined. CodeChunkEmbedding chunking strategy is implemented.

- Full session flow: `createSession` → `runTaskStartWorkflow` → `runOutputPipeline` → `endSession` (all int IDs)
- PII never in Postgres: `scrub()` removes before any `prisma.*.create()` call
- Task-type specific context: `loadContext` dispatches on `taskType` — CODING loads Notion tasks, ADRs, and branch info
- Output traceable: `WorkflowRun.taskId` (int FK) links output to its task
- Eval scaffolding: `evals/schema.ts` (dataset format with int IDs) + `evals/runner.ts` (stub)
- CodeChunkEmbedding: `services/code-chunker.ts` using `@langchain/textsplitters` RecursiveCharacterTextSplitter (512 tokens, 256 overlap)
- Embeddings: nomic-embed-text via Ollama, `vector(768)`
- Packaging: `llm/packaging/` renders skill templates into model-specific install formats (Claude, Ollama)
- Schema alignment: all IDs are `Int @id @default(autoincrement())`, `TaskPriority` (not `Priority`), `externalTaskId` (not `jiraKey`), `branch` + `repoId` FK (not `githubBranch`/`githubRepo`), `ActionItem` model (not `String[]`), `TaskStatus` includes `BLOCKED`
- Prisma: generator `"prisma-client"`, `output = "../generated/prisma"`, imports from `../../generated/prisma/index.js`

- [ ] **Step 8.4: Final commit**

```bash
git add .
git commit -m "chore: step 5 complete — full system end-to-end contract passing"
```

---

## Troubleshooting

**`loadContext` calls integrations even when tokens are missing**
Each loader function checks for the token before calling — if `getIntegrationToken` returns `null`, the call is skipped. In tests, `getIntegrationToken` is mocked to return `'mock-token'` so the integration functions are called; mock the integrations themselves to control their return values.

**`wizard task end` hangs waiting for stdin**
The `task end` CLI command reads from stdin. Pipe the LLM's output: `echo '<llm output>' | wizard task end`. Or write the output to a file and use: `wizard task end < output.txt`.

**Skill template test fails — placeholder count mismatch**
The `SKILL_VARIABLES` map in `skill-templates.test.ts` must exactly match the placeholders in each template file. If you add or remove a placeholder from a template, update the corresponding entry in `SKILL_VARIABLES`.

**`evals/runner.ts` throws "not implemented" during tests**
This is correct. `runEvals` is intentionally a stub. Do not call it in tests. Tests can import `EvalDataset` and `EvalExample` types from `evals/schema.ts` without triggering the runner.

**Embedding dimensions mismatch**
All embeddings use `vector(768)` (nomic-embed-text via Ollama). There is no `openai` dependency for embeddings. If you see 1536-dimension errors, ensure you are using the Ollama embedding adapter.

**Import path errors — `@prisma/client` not found**
All imports from the generated Prisma client must use `../../generated/prisma/index.js`, not `@prisma/client`. The Prisma generator is configured as `"prisma-client"` with `output = "../generated/prisma"`.

**`TaskPriority` vs `Priority` type errors**
The enum is `TaskPriority` (LOW | MEDIUM | HIGH), not `Priority`. Update any references accordingly.

**`externalTaskId` vs `jiraKey` errors**
The field is `externalTaskId` on the Task model, not `jiraKey`. Jira's issue key (e.g. "PD-42") maps to this field.

**`ActionItem` vs `String[]` actionItems**
Meeting action items are stored as separate `ActionItem` records (own model with Int ID, meetingId FK, optional taskId FK), not as `String[]` on the Meeting model. The LLM output for `meeting_review` returns an array of objects; each becomes an `ActionItem` record.

**`branch` + `repoId` vs `githubBranch`/`githubRepo`**
Task links to a repository via `repoId` FK (Int, references `Repo` model) and stores the branch name in `branch` (String). There are no `githubBranch` or `githubRepo` fields.
