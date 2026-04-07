// core/output/process.ts
import { z } from 'zod'
import type { LLMRawOutput, ProcessedOutput, PipelineResult } from './types.js'
import { TASK_STATUS_VALUES } from '../../shared/types.js'

const ProcessedOutputSchema = z.object({
  taskId: z.number().int().positive(),
  summary: z.string().min(1),
  status: z.enum(TASK_STATUS_VALUES as unknown as [string, ...string[]]),
  meetingId: z.number().int().positive().optional().nullable().transform((v) => v ?? null),
  externalTaskId: z.string().optional().nullable().transform((v) => v ?? null),
  notes: z.string().optional().nullable().transform((v) => v ?? null),
})

/**
 * Extracts the first ```json ... ``` block from the LLM's raw output and
 * parses it into a ProcessedOutput. Returns ok: false on any failure.
 */
export function processOutput(raw: LLMRawOutput): PipelineResult<ProcessedOutput> {
  const match = raw.match(/```json\s*([\s\S]*?)```/)
  if (!match) {
    return { ok: false, reason: 'No JSON block found in LLM output' }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(match[1])
  } catch (err) {
    return { ok: false, reason: `Failed to parse JSON: ${String(err)}` }
  }

  const result = ProcessedOutputSchema.safeParse(parsed)
  if (!result.success) {
    const missing = result.error.issues.map((i) => i.path.join('.')).join(', ')
    return { ok: false, reason: `Schema validation failed — invalid fields: ${missing}` }
  }

  return { ok: true, value: result.data as ProcessedOutput }
}
