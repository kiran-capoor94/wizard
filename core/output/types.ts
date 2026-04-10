import type { TaskStatus } from '../../shared/types.js'

/**
 * The raw text the LLM produces. Wizard requires the LLM to output
 * a JSON block wrapped in triple backticks:
 *
 * ```json
 * { ... }
 * ```
 *
 * The pipeline extracts the first JSON block from this text.
 */
export type LLMRawOutput = string

/**
 * The structured output after parsing the LLM's JSON block.
 * Uses int IDs matching Prisma schema (Int @id @default(autoincrement())).
 */
export type ProcessedOutput = {
  taskId: number
  summary: string
  status: TaskStatus
  meetingId: number | null   // claimed attribution — may be wrong
  externalTaskId: string | null
  notes: string | null
}

/**
 * After transform: ProcessedOutput with resolved Postgres foreign keys confirmed.
 * All IDs are int (matching autoincrement schema).
 */
export type TransformedOutput = {
  taskId: number
  summary: string
  status: TaskStatus
  meetingId: number | null     // null if not provided or not found
  externalTaskId: string | null
  notes: string | null
}

/**
 * Result type for each pipeline step.
 */
export type PipelineResult<T> =
  | { ok: true; value: T }
  | { ok: false; reason: string }
