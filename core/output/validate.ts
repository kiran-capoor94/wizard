// core/output/validate.ts
import { z } from 'zod'
import type { TaskStatus, EmbeddingVector } from '../../shared/types.js'
import { TASK_STATUS_VALUES } from '../../shared/types.js'
import type { TransformedOutput, PipelineResult } from './types.js'

const TransformedOutputSchema = z.object({
  taskId: z.number().int().positive(),
  summary: z.string().min(1),
  status: z.enum(TASK_STATUS_VALUES as unknown as [TaskStatus, ...TaskStatus[]]),
  meetingId: z.number().int().positive().nullable(),
  externalTaskId: z.string().nullable(),
  notes: z.string().nullable(),
})

export type ValidateDeps = {
  computeEmbedding: (text: string) => Promise<PipelineResult<EmbeddingVector>>
  getCosineSimilarity: (taskId: number, queryVector: EmbeddingVector) => Promise<number | null>
  getAttributionThreshold: () => Promise<number | null>
}

/**
 * Validates a TransformedOutput against two checks:
 * 1. Schema contract — Zod validation of all fields
 * 2. Semantic attribution — pgvector similarity check if meetingId is claimed
 *
 * Repository and embedding functions are injected via deps for testability.
 * Production callers pass the real implementations; tests pass mocks.
 * Returns ok: false if either check fails. Does not throw.
 */
export async function validateOutput(
  output: TransformedOutput,
  deps: ValidateDeps
): Promise<PipelineResult<TransformedOutput>> {
  // 1. Schema contract check
  const schemaResult = TransformedOutputSchema.safeParse(output)
  if (!schemaResult.success) {
    const fields = schemaResult.error.issues.map((i) => i.path.join('.')).join(', ')
    return { ok: false, reason: `Schema contract failed — invalid fields: ${fields}` }
  }

  // 2. Semantic attribution check (only if meetingId is claimed)
  if (output.meetingId !== null) {
    const embResult = await deps.computeEmbedding(output.summary)
    if (embResult.ok) {
      const similarity = await deps.getCosineSimilarity(output.taskId, embResult.value)
      if (similarity !== null) {
        const threshold = await deps.getAttributionThreshold()
        // If threshold is null (not configured), skip attribution check
        if (threshold !== null && similarity < threshold) {
          return {
            ok: false,
            reason: `Attribution check failed — similarity ${similarity.toFixed(2)} below threshold ${threshold}`,
          }
        }
      }
    }
    // If embedding computation fails, skip attribution check (Ollama is infrastructure-optional)
  }

  return { ok: true, value: output }
}
