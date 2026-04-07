---
name: wizard-check-types
description: >
  Use when you want to check for type contract drift in the Wizard codebase. Detects re-declared
  Prisma enums, wrong nullability, string IDs, and embedding dimension mismatches.
  Invoke with /wizard-check-types.
---

# Type Contract Drift Detection

Check the Wizard codebase for type contract drift from the Prisma source of truth. Report findings in the format below.

## What To Check

### 1. Re-declared Prisma Enums

These enums must only exist in `prisma/schema.prisma` and be re-exported from `shared/types.ts`. They must never be re-declared as TypeScript enums or union types anywhere else:

`TaskStatus`, `TaskType`, `TaskPriority`, `SessionStatus`, `WorkflowStatus`, `NoteType`, `NoteParent`, `RepoProvider`

**How to check:**
- Use Grep to search for `enum TaskStatus`, `enum TaskType`, `enum TaskPriority`, `enum SessionStatus`, `enum WorkflowStatus`, `enum NoteType`, `enum NoteParent`, `enum RepoProvider` in all `.ts` files.
- Also search for these as union types: `type TaskStatus =`, `type TaskType =`, etc.
- Matches in `shared/types.ts` that are re-exports (`export { TaskStatus } from`) are fine.
- Matches in `generated/prisma/` are fine (Prisma-generated).
- Any other match is a FAIL — the enum is being re-declared.

### 2. Wrong Nullability

Prisma uses `null` for optional fields, not `undefined`. All optional fields in Wizard types must use `| null`.

**How to check:**
- Use Grep to search for `?: ` (optional property syntax) in type/interface definitions under `shared/`, `data/`, `services/`, `orchestrator/`, `llm/`, `core/`.
- For each match, check if the field corresponds to a nullable Prisma field. If it does, it should be `fieldName: Type | null` not `fieldName?: Type`.
- `undefined` is acceptable for function parameters that are truly optional. It is NOT acceptable for data types that mirror Prisma models.

### 3. String IDs

All entity IDs in Wizard are autoincrement integers, not strings.

**How to check:**
- Use Grep to search for `id: string`, `taskId: string`, `sessionId: string`, `meetingId: string`, `noteId: string`, `repoId: string`, `userId: string` in all `.ts` files under `shared/`, `data/`, `services/`, `orchestrator/`, `llm/`, `core/`.
- Each match is a FAIL. IDs must be `number`.

### 4. TaskContext Location

`TaskContext` must be defined in `shared/types.ts` only.

**How to check:**
- Use Grep to search for `interface TaskContext` or `type TaskContext` in all `.ts` files.
- A match in `shared/types.ts` is expected. Any other match is a FAIL.

### 5. Embedding Dimensions

All embeddings must be `vector(768)` — nomic-embed-text dimensions. Not 1536, not 384, not any other value.

**How to check:**
- Use Grep to search for `vector(` in all files under `prisma/`, `data/`, and any migration files.
- Every match must be `vector(768)`. Any other dimension is a FAIL.
- Also search for dimension constants: `1536`, `384`, `256` near embedding-related code in `llm/` and `data/`. Flag if they appear as vector dimensions.

## Output Format

```
## Type Contract Check

### PASS — Prisma enums not re-declared
### FAIL — Wrong nullability (2 issues)
- shared/types.ts:45 — taskId?: number should be taskId: number | null
- services/context.ts:12 — meetingId?: number should be meetingId: number | null

### PASS — IDs are integers
### PASS — TaskContext in shared/types.ts
### PASS — Embedding dimensions are vector(768)

Result: PASS / FAIL
```
