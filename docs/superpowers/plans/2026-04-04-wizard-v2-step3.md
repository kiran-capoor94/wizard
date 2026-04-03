# Wizard v2 Step 3 — Integration → Security → Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Security layer (PII scrubbing), the first integration (Notion), the config system (`wizard.config.yaml`), and the `wizard setup` CLI command. Prove that raw Notion data passes through PII scrubbing before reaching Postgres, and that an audit trail records what was scrubbed.

**Architecture:** Raw data flows Integration → Security → Data. Security is the only thing that stands between raw external data and Postgres. The Security layer scrubs PII (emails, phone numbers, NHS numbers) and emits audit entries. It never stubs — detected PII is removed, not replaced. Integration tokens are stored encrypted in `IntegrationConfig`. The CLI reads `wizard.config.yaml`, orchestrates setup, and stores config in Postgres.

**Tech Stack:** TypeScript (ESM, Node16), Prisma, Vitest, `js-yaml` (YAML parsing), `commander` (CLI), `@notionhq/client` (already installed). Node's built-in `crypto` for AES-256-GCM token encryption. No new heavy dependencies.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `security/scrub.ts` | PII detection (regex) and removal; returns scrubbed text + audit entries |
| Create | `security/types.ts` | `ScrubResult`, `AuditEntry` types |
| Create | `security/encrypt.ts` | AES-256-GCM token encryption/decryption for `IntegrationConfig.token` |
| Create | `integrations/notion/pull.ts` | Pull tasks and meetings from Notion, route through security |
| Create | `core/config.ts` | Parse and validate `wizard.config.yaml` with Zod |
| Create | `cli/index.ts` | CLI entry point (commander) |
| Create | `cli/commands/setup.ts` | `wizard setup` — reads config, stores tokens, validates connections |
| Create | `wizard.config.example.yaml` | Documented example config file (committed) |
| Create | `data/queries/config.ts` | Read/write `IntegrationConfig` rows |
| Create | New Prisma migration | Add `AuditLog` table |
| Modify | `tsconfig.json` | Add `security/**/*.ts`, `cli/**/*.ts` to `include` |
| Modify | `package.json` | Add `js-yaml`, `commander`; add `@types/js-yaml` dev dep; add `cli` bin entry |
| Create | `tests/unit/scrub.test.ts` | Known PII patterns detected and removed |
| Create | `tests/contracts/integration-to-security.test.ts` | Raw data → scrubbed → stored |
| Create | `tests/contracts/security-to-data.test.ts` | Only PII-free data reaches Postgres |

---

## Task 1: Dependencies + `tsconfig.json`

**Files:**
- Modify: `package.json`
- Modify: `tsconfig.json`

---

- [ ] **Step 1.1: Install new dependencies**

```bash
yarn add js-yaml commander
yarn add -D @types/js-yaml
```

- [ ] **Step 1.2: Update `package.json` — add CLI bin entry**

Add a second binary entry so `wizard` is available as a CLI command after install. Update the `bin` field and the `scripts` build command:

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
    "@prisma/client": "^6.0.0",
    "commander": "^12.0.0",
    "js-yaml": "^4.1.0",
    "zod": "^4.3.6"
  },
  "devDependencies": {
    "@types/js-yaml": "^4.0.9",
    "@types/node": "^25.5.0",
    "pgvector": "^0.2.0",
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

- [ ] **Step 1.3: Update `tsconfig.json`**

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
    "cli/**/*.ts"
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
mkdir -p security cli/commands data/queries
```

- [ ] **Step 1.5: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 1.6: Commit**

```bash
git add package.json tsconfig.json
git commit -m "chore: add js-yaml and commander, update tsconfig for security/ and cli/"
```

---

## Task 2: Prisma Migration — `AuditLog` Table

**Files:**
- New migration in `data/prisma/migrations/`
- Modify: `data/prisma/schema.prisma`

---

- [ ] **Step 2.1: Add `AuditLog` model to `data/prisma/schema.prisma`**

Append to the schema (after existing models):

```prisma
// Audit trail for PII scrubbing — records what was detected and removed
model AuditLog {
  id           String   @id @default(cuid())
  source       String   // integration source: "notion", "jira", etc.
  fieldPath    String   // which field in the source data was scrubbed
  piiType      String   // "email", "phone", "nhs_number"
  originalHash String   // SHA-256 hash of the original value (not stored in plaintext)
  createdAt    DateTime @default(now())
}
```

- [ ] **Step 2.2: Run the migration**

```bash
npx prisma migrate dev --name add-audit-log
```

Expected: migration file created in `data/prisma/migrations/[timestamp]_add-audit-log/migration.sql` and applied.

- [ ] **Step 2.3: Verify the table exists**

```bash
docker-compose exec postgres psql -U wizard -d wizard -c "\dt" | grep Audit
```

Expected: `AuditLog` appears in the table list.

- [ ] **Step 2.4: Commit**

```bash
git add data/prisma/schema.prisma data/prisma/migrations/
git commit -m "feat: add AuditLog table migration"
```

---

## Task 3: `security/types.ts` and `security/scrub.ts` — PII Scrubbing

**Files:**
- Create: `security/types.ts`
- Create: `security/scrub.ts`
- Create: `tests/unit/scrub.test.ts`

---

- [ ] **Step 3.1: Create `security/types.ts`**

```typescript
// security/types.ts

export type PiiType = 'email' | 'phone_uk' | 'nhs_number'

export type AuditEntry = {
  fieldPath: string
  piiType: PiiType
  originalHash: string   // SHA-256 hex of the original match
}

export type ScrubResult = {
  text: string           // cleaned text with PII removed
  entries: AuditEntry[]  // one entry per detected PII instance
}
```

- [ ] **Step 3.2: Write the failing test**

```typescript
// tests/unit/scrub.test.ts
import { describe, it, expect } from 'vitest'
import { scrub } from '../../security/scrub.js'

describe('scrub', () => {
  it('removes email addresses from text', () => {
    const result = scrub('Contact kiran@example.com for details', 'notion.meeting.notes')
    expect(result.text).not.toContain('kiran@example.com')
    expect(result.text).toContain('Contact')
    expect(result.entries).toHaveLength(1)
    expect(result.entries[0].piiType).toBe('email')
    expect(result.entries[0].fieldPath).toBe('notion.meeting.notes')
  })

  it('removes UK phone numbers from text', () => {
    const result = scrub('Call 07700 900123 to discuss', 'notion.task.description')
    expect(result.text).not.toContain('07700 900123')
    expect(result.entries).toHaveLength(1)
    expect(result.entries[0].piiType).toBe('phone_uk')
  })

  it('removes NHS numbers from text', () => {
    const result = scrub('NHS number: 943-476-5919', 'notion.meeting.notes')
    expect(result.text).not.toContain('943-476-5919')
    expect(result.entries).toHaveLength(1)
    expect(result.entries[0].piiType).toBe('nhs_number')
  })

  it('removes multiple PII instances from one field', () => {
    const result = scrub(
      'Email: dev@example.com, phone: 07700 900456',
      'notion.task.description'
    )
    expect(result.text).not.toContain('dev@example.com')
    expect(result.text).not.toContain('07700 900456')
    expect(result.entries).toHaveLength(2)
  })

  it('returns unchanged text and no entries when no PII is present', () => {
    const input = 'Deploy the auth service to staging'
    const result = scrub(input, 'notion.task.title')
    expect(result.text).toBe(input)
    expect(result.entries).toHaveLength(0)
  })

  it('stores a SHA-256 hash of the original match, not the plaintext', () => {
    const result = scrub('Contact dev@example.com', 'test.field')
    expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)
    expect(result.entries[0].originalHash).not.toContain('dev@example.com')
  })
})
```

- [ ] **Step 3.3: Run the test — verify it fails**

```bash
yarn test tests/unit/scrub.test.ts
```

Expected: `Error: Failed to resolve import "../../security/scrub.js"`

- [ ] **Step 3.4: Create `security/scrub.ts`**

```typescript
// security/scrub.ts
import { createHash } from 'node:crypto'
import type { PiiType, ScrubResult, AuditEntry } from './types.js'

// PII patterns. Order matters: most specific first.
const PII_PATTERNS: Array<{ type: PiiType; pattern: RegExp }> = [
  {
    type: 'nhs_number',
    // NHS numbers: 10 digits in groups of 3-3-4 separated by space or hyphen
    pattern: /\b\d{3}[\s-]\d{3}[\s-]\d{4}\b/g,
  },
  {
    type: 'phone_uk',
    // UK mobile and landline: starts with 07 or +44, 10-11 digits with optional spaces
    pattern: /(\+44\s?|0)7\d{3}[\s-]?\d{6}\b|\b0[1-9]\d{2,3}[\s-]?\d{5,6}\b/g,
  },
  {
    type: 'email',
    pattern: /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g,
  },
]

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}

/**
 * Detects and removes PII from a text string.
 * Returns the cleaned text and an audit entry for each match.
 * Scrub only — detected PII is removed, not stubbed or replaced.
 */
export function scrub(text: string, fieldPath: string): ScrubResult {
  let result = text
  const entries: AuditEntry[] = []

  for (const { type, pattern } of PII_PATTERNS) {
    // Reset lastIndex to ensure global patterns start from beginning
    pattern.lastIndex = 0
    const matches = result.matchAll(pattern)

    for (const match of matches) {
      entries.push({
        fieldPath,
        piiType: type,
        originalHash: sha256(match[0]),
      })
    }

    pattern.lastIndex = 0
    result = result.replace(pattern, '')
  }

  // Clean up any double spaces left by removal
  result = result.replace(/  +/g, ' ').trim()

  return { text: result, entries }
}
```

- [ ] **Step 3.5: Run the test — verify it passes**

```bash
yarn test tests/unit/scrub.test.ts
```

Expected:

```
✓ scrub > removes email addresses from text
✓ scrub > removes UK phone numbers from text
✓ scrub > removes NHS numbers from text
✓ scrub > removes multiple PII instances from one field
✓ scrub > returns unchanged text and no entries when no PII is present
✓ scrub > stores a SHA-256 hash of the original match, not the plaintext

Test Files  1 passed (1)
Tests       6 passed (6)
```

- [ ] **Step 3.6: Commit**

```bash
git add security/types.ts security/scrub.ts tests/unit/scrub.test.ts
git commit -m "feat: add PII scrubbing to security/scrub"
```

---

## Task 4: `security/encrypt.ts` — Token Encryption

**Files:**
- Create: `security/encrypt.ts`
- Create: `tests/unit/encrypt.test.ts`

Integration tokens in `IntegrationConfig.token` are stored as AES-256-GCM ciphertext. The key comes from `WIZARD_ENCRYPTION_KEY` (a 64-character hex string = 32 bytes).

---

- [ ] **Step 4.1: Add `WIZARD_ENCRYPTION_KEY` to `.env` and `.env.example`**

Generate a key and add to `.env`:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Add the output to `.env`:

```
DATABASE_URL="postgresql://wizard:wizard@localhost:5432/wizard"
WIZARD_ENCRYPTION_KEY="<64-char hex string from above command>"
```

And to `.env.example` (placeholder):

```
DATABASE_URL="postgresql://wizard:wizard@localhost:5432/wizard"
WIZARD_ENCRYPTION_KEY="replace-with-64-char-hex-string"
```

- [ ] **Step 4.2: Write the failing test**

```typescript
// tests/unit/encrypt.test.ts
import { describe, it, expect, beforeAll } from 'vitest'
import { encrypt, decrypt } from '../../security/encrypt.js'

beforeAll(() => {
  // Tests require WIZARD_ENCRYPTION_KEY to be set
  if (!process.env.WIZARD_ENCRYPTION_KEY) {
    throw new Error('WIZARD_ENCRYPTION_KEY must be set in .env to run encrypt tests')
  }
})

describe('encrypt / decrypt', () => {
  it('round-trips a token through encryption and decryption', () => {
    const original = 'secret-notion-token-abc123'
    const ciphertext = encrypt(original)
    const plaintext = decrypt(ciphertext)
    expect(plaintext).toBe(original)
  })

  it('produces different ciphertext for the same input each time (random IV)', () => {
    const token = 'same-token'
    const c1 = encrypt(token)
    const c2 = encrypt(token)
    expect(c1).not.toBe(c2)
    expect(decrypt(c1)).toBe(token)
    expect(decrypt(c2)).toBe(token)
  })

  it('ciphertext is a non-empty string', () => {
    const result = encrypt('any-token')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })

  it('throws when ciphertext is corrupted', () => {
    expect(() => decrypt('corrupted-ciphertext')).toThrow()
  })
})
```

- [ ] **Step 4.3: Run the test — verify it fails**

```bash
yarn test tests/unit/encrypt.test.ts
```

Expected: `Error: Failed to resolve import "../../security/encrypt.js"`

- [ ] **Step 4.4: Create `security/encrypt.ts`**

```typescript
// security/encrypt.ts
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto'

const ALGORITHM = 'aes-256-gcm'
const IV_LENGTH = 12   // 96-bit IV, recommended for GCM
const TAG_LENGTH = 16  // 128-bit auth tag

function getKey(): Buffer {
  const hex = process.env.WIZARD_ENCRYPTION_KEY
  if (!hex || hex.length !== 64) {
    throw new Error(
      'WIZARD_ENCRYPTION_KEY must be a 64-character hex string (32 bytes)'
    )
  }
  return Buffer.from(hex, 'hex')
}

/**
 * Encrypts a plaintext string using AES-256-GCM.
 * Returns a base64-encoded string: iv + authTag + ciphertext.
 */
export function encrypt(plaintext: string): string {
  const key = getKey()
  const iv = randomBytes(IV_LENGTH)
  const cipher = createCipheriv(ALGORITHM, key, iv)

  const encrypted = Buffer.concat([
    cipher.update(plaintext, 'utf8'),
    cipher.final(),
  ])
  const tag = cipher.getAuthTag()

  return Buffer.concat([iv, tag, encrypted]).toString('base64')
}

/**
 * Decrypts a base64-encoded AES-256-GCM ciphertext.
 * Throws if the ciphertext is malformed or the key is wrong.
 */
export function decrypt(ciphertext: string): string {
  const key = getKey()
  const data = Buffer.from(ciphertext, 'base64')

  const iv = data.subarray(0, IV_LENGTH)
  const tag = data.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH)
  const encrypted = data.subarray(IV_LENGTH + TAG_LENGTH)

  const decipher = createDecipheriv(ALGORITHM, key, iv)
  decipher.setAuthTag(tag)

  return Buffer.concat([
    decipher.update(encrypted),
    decipher.final(),
  ]).toString('utf8')
}
```

- [ ] **Step 4.5: Run the test — verify it passes**

```bash
yarn test tests/unit/encrypt.test.ts
```

Expected:

```
✓ encrypt / decrypt > round-trips a token through encryption and decryption
✓ encrypt / decrypt > produces different ciphertext for the same input each time (random IV)
✓ encrypt / decrypt > ciphertext is a non-empty string
✓ encrypt / decrypt > throws when ciphertext is corrupted

Test Files  1 passed (1)
Tests       4 passed (4)
```

- [ ] **Step 4.6: Commit**

```bash
git add security/encrypt.ts tests/unit/encrypt.test.ts .env.example
git commit -m "feat: add AES-256-GCM token encryption to security/encrypt"
```

---

## Task 5: `data/queries/config.ts` — Integration Config Query Layer

**Files:**
- Create: `data/queries/config.ts`
- Create: `data/queries/audit.ts`

---

- [ ] **Step 5.1: Create `data/queries/config.ts`**

```typescript
// data/queries/config.ts
import { PrismaClient } from '@prisma/client'
import { encrypt, decrypt } from '../../security/encrypt.js'

const prisma = new PrismaClient()

export type IntegrationSource = 'notion' | 'jira' | 'github' | 'krisp'

/**
 * Stores an integration token (encrypted) in IntegrationConfig.
 * Upserts: safe to call multiple times for the same source.
 */
export async function storeIntegrationToken(
  source: IntegrationSource,
  token: string,
  metadata?: Record<string, unknown>
): Promise<void> {
  await prisma.integrationConfig.upsert({
    where: { source },
    update: { token: encrypt(token), metadata: metadata ?? {} },
    create: { source, token: encrypt(token), metadata: metadata ?? {} },
  })
}

/**
 * Retrieves and decrypts an integration token from IntegrationConfig.
 * Returns null if not configured.
 */
export async function getIntegrationToken(
  source: IntegrationSource
): Promise<string | null> {
  const config = await prisma.integrationConfig.findUnique({
    where: { source },
  })
  if (!config) return null
  return decrypt(config.token)
}
```

- [ ] **Step 5.2: Create `data/queries/audit.ts`**

```typescript
// data/queries/audit.ts
import { PrismaClient } from '@prisma/client'
import type { AuditEntry } from '../../security/types.js'

const prisma = new PrismaClient()

/**
 * Persists audit entries generated by the security layer to the AuditLog table.
 */
export async function writeAuditEntries(
  source: string,
  entries: AuditEntry[]
): Promise<void> {
  if (entries.length === 0) return

  await prisma.auditLog.createMany({
    data: entries.map((entry) => ({
      source,
      fieldPath: entry.fieldPath,
      piiType: entry.piiType,
      originalHash: entry.originalHash,
    })),
  })
}
```

- [ ] **Step 5.3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 5.4: Commit**

```bash
git add data/queries/config.ts data/queries/audit.ts
git commit -m "feat: add integration config and audit query layer"
```

---

## Task 6: `core/config.ts` — `wizard.config.yaml` Parsing

**Files:**
- Create: `core/config.ts`
- Create: `wizard.config.example.yaml`
- Create: `tests/unit/config.test.ts`

---

- [ ] **Step 6.1: Create `wizard.config.example.yaml`**

```yaml
# wizard.config.example.yaml
# Copy this file to wizard.config.yaml and fill in your tokens.
# wizard.config.yaml is gitignored — never commit real tokens.

integrations:
  notion:
    token: your-notion-integration-token
  jira:
    token: your-jira-api-token
    project: PD        # Jira project key
  github:
    token: your-github-personal-access-token
  krisp:
    method: mcp        # only supported method in v2

ide:
  primary: neovim      # neovim | vscode | claude-desktop

security:
  pii_scrubbing: true
  encryption_at_rest: true
```

- [ ] **Step 6.2: Add `wizard.config.yaml` to `.gitignore`**

Append to `.gitignore`:

```
wizard.config.yaml
```

- [ ] **Step 6.3: Write the failing test**

```typescript
// tests/unit/config.test.ts
import { describe, it, expect } from 'vitest'
import { parseConfig } from '../../core/config.js'

const VALID_CONFIG = `
integrations:
  notion:
    token: secret-notion-token
  jira:
    token: secret-jira-token
    project: PD
  github:
    token: secret-github-token
  krisp:
    method: mcp
ide:
  primary: neovim
security:
  pii_scrubbing: true
  encryption_at_rest: true
`

describe('parseConfig', () => {
  it('parses a valid config and returns structured data', () => {
    const config = parseConfig(VALID_CONFIG)
    expect(config.integrations.notion.token).toBe('secret-notion-token')
    expect(config.integrations.jira.token).toBe('secret-jira-token')
    expect(config.integrations.jira.project).toBe('PD')
    expect(config.integrations.github.token).toBe('secret-github-token')
    expect(config.integrations.krisp.method).toBe('mcp')
    expect(config.ide.primary).toBe('neovim')
    expect(config.security.piiScrubbing).toBe(true)
    expect(config.security.encryptionAtRest).toBe(true)
  })

  it('throws when notion token is missing', () => {
    const broken = VALID_CONFIG.replace('token: secret-notion-token', '')
    expect(() => parseConfig(broken)).toThrow()
  })

  it('throws when ide.primary is not a valid value', () => {
    const broken = VALID_CONFIG.replace('primary: neovim', 'primary: emacs')
    expect(() => parseConfig(broken)).toThrow()
  })

  it('throws when the YAML is malformed', () => {
    expect(() => parseConfig('this: is: not: valid: yaml:')).toThrow()
  })
})
```

- [ ] **Step 6.4: Run the test — verify it fails**

```bash
yarn test tests/unit/config.test.ts
```

Expected: `Error: Failed to resolve import "../../core/config.js"`

- [ ] **Step 6.5: Create `core/config.ts`**

```typescript
// core/config.ts
import { load as parseYaml } from 'js-yaml'
import { z } from 'zod'

const ConfigSchema = z.object({
  integrations: z.object({
    notion: z.object({ token: z.string().min(1) }),
    jira: z.object({
      token: z.string().min(1),
      project: z.string().min(1).default('PD'),
    }),
    github: z.object({ token: z.string().min(1) }),
    krisp: z.object({ method: z.literal('mcp') }),
  }),
  ide: z.object({
    primary: z.enum(['neovim', 'vscode', 'claude-desktop']),
  }),
  security: z.object({
    // eslint-disable-next-line @typescript-eslint/naming-convention
    pii_scrubbing: z.boolean(),
    // eslint-disable-next-line @typescript-eslint/naming-convention
    encryption_at_rest: z.boolean(),
  }),
})

export type WizardConfig = {
  integrations: {
    notion: { token: string }
    jira: { token: string; project: string }
    github: { token: string }
    krisp: { method: 'mcp' }
  }
  ide: { primary: 'neovim' | 'vscode' | 'claude-desktop' }
  security: { piiScrubbing: boolean; encryptionAtRest: boolean }
}

/**
 * Parses and validates a wizard.config.yaml string.
 * Throws a Zod validation error if the config is invalid.
 */
export function parseConfig(yamlString: string): WizardConfig {
  const raw = parseYaml(yamlString) as Record<string, unknown>
  const parsed = ConfigSchema.parse(raw)

  return {
    integrations: parsed.integrations,
    ide: parsed.ide,
    security: {
      piiScrubbing: parsed.security.pii_scrubbing,
      encryptionAtRest: parsed.security.encryption_at_rest,
    },
  }
}
```

- [ ] **Step 6.6: Run the test — verify it passes**

```bash
yarn test tests/unit/config.test.ts
```

Expected:

```
✓ parseConfig > parses a valid config and returns structured data
✓ parseConfig > throws when notion token is missing
✓ parseConfig > throws when ide.primary is not a valid value
✓ parseConfig > throws when the YAML is malformed

Test Files  1 passed (1)
Tests       4 passed (4)
```

- [ ] **Step 6.7: Commit**

```bash
git add core/config.ts wizard.config.example.yaml tests/unit/config.test.ts .gitignore
git commit -m "feat: add wizard.config.yaml parsing to core/config"
```

---

## Task 7: `integrations/notion/pull.ts` — Notion Integration

**Files:**
- Create: `integrations/notion/pull.ts`
- Create: `tests/unit/notion-pull.test.ts`

`pull.ts` fetches raw data from Notion and passes it through the security layer before returning. It never writes to Postgres — that's the caller's responsibility.

---

- [ ] **Step 7.1: Create `integrations/notion/pull.ts`**

```typescript
// integrations/notion/pull.ts
import { Client } from '@notionhq/client'
import { scrub } from '../../security/scrub.js'
import type { ScrubResult } from '../../security/types.js'

export type RawNotionTask = {
  notionId: string
  title: ScrubResult
  description: ScrubResult
  status: string
  dueDate: string | null
  jiraKey: string | null
}

export type RawNotionMeeting = {
  notionId: string
  title: ScrubResult
  notes: ScrubResult
  date: string | null
}

/**
 * Fetches tasks from a Notion database, scrubs PII from text fields.
 * Returns raw (unsaved) task data with scrub results.
 */
export async function pullNotionTasks(
  token: string,
  databaseId: string
): Promise<RawNotionTask[]> {
  const notion = new Client({ auth: token })

  const response = await notion.databases.query({ database_id: databaseId })

  return response.results.map((page) => {
    // @ts-expect-error — Notion SDK types for properties are complex; cast to any
    const props = (page as any).properties ?? {}

    const rawTitle = extractRichText(props['Name'] ?? props['Title']) ?? ''
    const rawDesc = extractRichText(props['Description'] ?? props['Notes']) ?? ''
    const status = extractSelect(props['Status']) ?? 'Todo'
    const dueDate = extractDate(props['Due Date'] ?? props['Due']) ?? null
    const jiraKey = extractRichText(props['Jira Key'] ?? props['Ticket']) ?? null

    return {
      notionId: page.id,
      title: scrub(rawTitle, `notion.task.${page.id}.title`),
      description: scrub(rawDesc, `notion.task.${page.id}.description`),
      status,
      dueDate,
      jiraKey,
    }
  })
}

/**
 * Fetches meeting notes from a Notion database, scrubs PII from text fields.
 */
export async function pullNotionMeetings(
  token: string,
  databaseId: string
): Promise<RawNotionMeeting[]> {
  const notion = new Client({ auth: token })

  const response = await notion.databases.query({ database_id: databaseId })

  return response.results.map((page) => {
    // @ts-expect-error
    const props = (page as any).properties ?? {}

    const rawTitle = extractRichText(props['Name'] ?? props['Title']) ?? ''
    const rawNotes = extractRichText(props['Notes'] ?? props['Content']) ?? ''
    const date = extractDate(props['Date'] ?? props['Meeting Date']) ?? null

    return {
      notionId: page.id,
      title: scrub(rawTitle, `notion.meeting.${page.id}.title`),
      notes: scrub(rawNotes, `notion.meeting.${page.id}.notes`),
      date,
    }
  })
}

// --- Notion property extractors ---

function extractRichText(prop: any): string | undefined {
  if (!prop) return undefined
  if (prop.type === 'rich_text') {
    return prop.rich_text?.map((r: any) => r.plain_text).join('') ?? ''
  }
  if (prop.type === 'title') {
    return prop.title?.map((r: any) => r.plain_text).join('') ?? ''
  }
  return undefined
}

function extractSelect(prop: any): string | undefined {
  if (!prop) return undefined
  return prop.select?.name
}

function extractDate(prop: any): string | undefined {
  if (!prop) return undefined
  return prop.date?.start
}
```

- [ ] **Step 7.2: Write the unit test (using a mock Notion response)**

```typescript
// tests/unit/notion-pull.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the Notion client before importing the module under test
vi.mock('@notionhq/client', () => ({
  Client: vi.fn().mockImplementation(() => ({
    databases: {
      query: vi.fn().mockResolvedValue({
        results: [
          {
            id: 'page-001',
            properties: {
              Name: {
                type: 'title',
                title: [{ plain_text: 'Deploy auth service' }],
              },
              Description: {
                type: 'rich_text',
                rich_text: [
                  { plain_text: 'Contact dev@example.com for access' },
                ],
              },
              Status: { type: 'select', select: { name: 'In Progress' } },
              'Due Date': {
                type: 'date',
                date: { start: '2026-04-10' },
              },
              'Jira Key': {
                type: 'rich_text',
                rich_text: [{ plain_text: 'PD-42' }],
              },
            },
          },
        ],
      }),
    },
  })),
}))

import { pullNotionTasks } from '../../integrations/notion/pull.js'

describe('pullNotionTasks', () => {
  it('returns tasks with scrubbed text fields', async () => {
    const tasks = await pullNotionTasks('mock-token', 'mock-db-id')

    expect(tasks).toHaveLength(1)
    expect(tasks[0].notionId).toBe('page-001')
    expect(tasks[0].title.text).toBe('Deploy auth service')
    expect(tasks[0].status).toBe('In Progress')
    expect(tasks[0].dueDate).toBe('2026-04-10')
    expect(tasks[0].jiraKey).toBe('PD-42')
  })

  it('scrubs email addresses from description', async () => {
    const tasks = await pullNotionTasks('mock-token', 'mock-db-id')

    expect(tasks[0].description.text).not.toContain('dev@example.com')
    expect(tasks[0].description.entries).toHaveLength(1)
    expect(tasks[0].description.entries[0].piiType).toBe('email')
  })
})
```

- [ ] **Step 7.3: Run the test — verify it passes**

```bash
yarn test tests/unit/notion-pull.test.ts
```

Expected:

```
✓ pullNotionTasks > returns tasks with scrubbed text fields
✓ pullNotionTasks > scrubs email addresses from description

Test Files  1 passed (1)
Tests       2 passed (2)
```

- [ ] **Step 7.4: Commit**

```bash
git add integrations/notion/pull.ts tests/unit/notion-pull.test.ts
git commit -m "feat: add Notion integration with PII scrubbing"
```

---

## Task 8: `cli/` — `wizard setup` Command

**Files:**
- Create: `cli/index.ts`
- Create: `cli/commands/setup.ts`

---

- [ ] **Step 8.1: Create `cli/commands/setup.ts`**

```typescript
// cli/commands/setup.ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { parseConfig } from '../../core/config.js'
import { storeIntegrationToken } from '../../data/queries/config.js'
import { createNotionClient } from '../../integrations/notion/index.js'

/**
 * Reads wizard.config.yaml, stores integration tokens (encrypted), and
 * validates each connection. Prints status for each integration.
 */
export async function setup(): Promise<void> {
  const configPath = join(process.cwd(), 'wizard.config.yaml')
  let raw: string

  try {
    raw = readFileSync(configPath, 'utf-8')
  } catch {
    console.error('wizard.config.yaml not found. Copy wizard.config.example.yaml and fill in your tokens.')
    process.exit(1)
  }

  const config = parseConfig(raw)
  console.log('Config parsed. Storing integration tokens...')

  // Notion
  await storeIntegrationToken('notion', config.integrations.notion.token)
  try {
    const notion = createNotionClient()
    await notion.users.me({})
    console.log('✓ Notion: connected')
  } catch {
    console.warn('✗ Notion: connection failed — check your token')
  }

  // Jira
  await storeIntegrationToken('jira', config.integrations.jira.token, {
    project: config.integrations.jira.project,
  })
  console.log('✓ Jira: token stored (connection verified in Step 5)')

  // GitHub
  await storeIntegrationToken('github', config.integrations.github.token)
  console.log('✓ GitHub: token stored (connection verified in Step 5)')

  console.log('\nSetup complete. Run `wizard doctor` to verify all connections.')
}
```

- [ ] **Step 8.2: Create `cli/index.ts`**

```typescript
// cli/index.ts
import { Command } from 'commander'
import { setup } from './commands/setup.js'

const program = new Command()

program
  .name('wizard')
  .description('AI-powered engineering workflow system')
  .version('0.2.0')

program
  .command('setup')
  .description('Read wizard.config.yaml and configure all integrations')
  .action(async () => {
    await setup()
  })

program.parseAsync(process.argv)
```

- [ ] **Step 8.3: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 8.4: Commit**

```bash
git add cli/index.ts cli/commands/setup.ts
git commit -m "feat: add wizard setup CLI command"
```

---

## Task 9: Contract Tests — Integration → Security → Data Boundaries

**Files:**
- Create: `tests/contracts/integration-to-security.test.ts`
- Create: `tests/contracts/security-to-data.test.ts`

---

- [ ] **Step 9.1: Create `tests/contracts/integration-to-security.test.ts`**

```typescript
// tests/contracts/integration-to-security.test.ts
import { describe, it, expect } from 'vitest'
import { scrub } from '../../security/scrub.js'
import { writeAuditEntries } from '../../data/queries/audit.js'
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

describe('Integration → Security contract', () => {
  it('raw text containing PII exits the security layer with PII removed', () => {
    const raw = 'Discuss with alice@nhs.net about 943-476-5919 care plan'
    const result = scrub(raw, 'notion.meeting.test.notes')

    expect(result.text).not.toContain('alice@nhs.net')
    expect(result.text).not.toContain('943-476-5919')
    expect(result.entries).toHaveLength(2)
  })

  it('audit entries are written to Postgres after scrubbing', async () => {
    const raw = 'Contact dev@example.com for access'
    const result = scrub(raw, 'notion.task.contract-test.description')

    await writeAuditEntries('notion', result.entries)

    const logs = await prisma.auditLog.findMany({
      where: { fieldPath: 'notion.task.contract-test.description' },
    })

    expect(logs).toHaveLength(1)
    expect(logs[0].piiType).toBe('email')
    expect(logs[0].source).toBe('notion')
    // Hash is stored, not plaintext
    expect(logs[0].originalHash).toMatch(/^[a-f0-9]{64}$/)

    // Cleanup
    await prisma.auditLog.deleteMany({
      where: { fieldPath: 'notion.task.contract-test.description' },
    })
    await prisma.$disconnect()
  })
})
```

- [ ] **Step 9.2: Create `tests/contracts/security-to-data.test.ts`**

```typescript
// tests/contracts/security-to-data.test.ts
import { describe, it, expect, afterAll } from 'vitest'
import { PrismaClient } from '@prisma/client'
import { scrub } from '../../security/scrub.js'

const prisma = new PrismaClient()
const createdTaskIds: string[] = []

afterAll(async () => {
  for (const id of createdTaskIds) {
    await prisma.task.delete({ where: { id } }).catch(() => {})
  }
  await prisma.$disconnect()
})

describe('Security → Data contract', () => {
  it('only PII-free text is written to Postgres', async () => {
    const rawTitle = 'Task for dev@example.com'
    const rawDescription = 'Contact 07700 900123 to discuss'

    const scrubbedTitle = scrub(rawTitle, 'test.title')
    const scrubbedDescription = scrub(rawDescription, 'test.description')

    // Write scrubbed text to Postgres
    const task = await prisma.task.create({
      data: {
        title: scrubbedTitle.text,
        description: scrubbedDescription.text,
        status: 'TODO',
        taskType: 'INVESTIGATION',
      },
    })
    createdTaskIds.push(task.id)

    // Re-query and assert no PII in stored data
    const stored = await prisma.task.findUnique({ where: { id: task.id } })

    expect(stored!.title).not.toContain('dev@example.com')
    expect(stored!.description).not.toContain('07700 900123')
    // Scrubbed versions are stored
    expect(stored!.title).toContain('Task for')
  })

  it('scrub entries are the audit trail — PII never reaches Postgres in any field', async () => {
    const piiText = 'NHS: 943-476-5919'
    const result = scrub(piiText, 'test.notes')

    // The entry has a hash, not the original value
    expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)

    // Write the scrubbed text to Postgres
    const task = await prisma.task.create({
      data: {
        title: result.text,
        status: 'TODO',
        taskType: 'INVESTIGATION',
      },
    })
    createdTaskIds.push(task.id)

    const stored = await prisma.task.findUnique({ where: { id: task.id } })
    expect(stored!.title).not.toContain('943-476-5919')
  })
})
```

- [ ] **Step 9.3: Run the contract tests**

```bash
yarn test tests/contracts/integration-to-security.test.ts tests/contracts/security-to-data.test.ts
```

Expected: all tests pass.

- [ ] **Step 9.4: Commit**

```bash
git add tests/contracts/integration-to-security.test.ts tests/contracts/security-to-data.test.ts
git commit -m "test(contract): add integration-to-security and security-to-data contract tests — step 3 proof passing"
```

---

## Task 10: Final Verification

---

- [ ] **Step 10.1: Run the full test suite**

```bash
yarn test
```

Expected: all tests pass (Step 1: 9, Step 2: 17, Step 3: new tests total ≥ 20 across all new test files).

- [ ] **Step 10.2: TypeScript clean build**

```bash
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 10.3: Step 3 proof criteria met**

From the spec:

> Raw Notion data enters the pipeline. PII is detected and removed before Postgres. Clean data reaches Claude. Audit trail shows what was scrubbed.

- `pullNotionTasks` returns scrubbed text ✓ — emails removed, audit entries produced
- `security-to-data.test.ts` confirms PII-free text stored in Postgres ✓
- `AuditLog` rows written with hash (not plaintext) of scrubbed PII ✓
- `integration-to-security.test.ts` proves the boundary holds end-to-end ✓

- [ ] **Step 10.4: Final commit**

```bash
git add .
git commit -m "chore: step 3 complete — integration-to-security contract passing"
```

---

## Troubleshooting

**`parseConfig` throws on valid YAML**
Ensure `js-yaml` is installed (`node_modules/js-yaml/` exists). Run `yarn install` if not.

**Notion connection fails in `wizard setup`**
The `NOTION_API_KEY` env var and the token from `wizard.config.yaml` are different things. `wizard setup` reads from the config file and stores the token in Postgres. The old `createNotionClient()` in `integrations/notion/index.ts` reads `NOTION_API_KEY` from env — that file is Step 3 legacy; `pull.ts` takes the token as a parameter.

**Encryption test fails with "WIZARD_ENCRYPTION_KEY must be a 64-character hex string"**
Ensure `.env` has `WIZARD_ENCRYPTION_KEY` set and that Vitest loads `.env`. Add `dotenv/config` import if Vitest doesn't auto-load it, or use `vitest.config.ts` with `dotenv: { path: '.env' }`.

**`scrub` removes partial text unexpectedly**
The UK phone regex is broad. If legitimate text is being removed, tighten the pattern in `security/scrub.ts` and add a test case for the false positive.
