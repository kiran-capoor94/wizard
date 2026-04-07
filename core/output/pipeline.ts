// core/output/pipeline.ts
import { processOutput } from './process.js'
import { transformOutput } from './transform.js'
import { validateOutput } from './validate.js'
import { storeOutput } from './store.js'
import { computeEmbedding } from './embeddings.js'
import { getCosineSimilarity, getAttributionThreshold } from '../../data/repositories/embeddings.js'
import type { LLMRawOutput, PipelineResult } from './types.js'

export type PipelineSuccess = { workflowRunId: number }

/**
 * Runs the LLM's raw output through the full pipeline:
 * process → transform → validate → store
 *
 * Each step returns ok: false on failure — the pipeline stops immediately
 * and returns the reason. No partial writes occur.
 */
export async function runOutputPipeline(
  raw: LLMRawOutput
): Promise<PipelineResult<PipelineSuccess>> {
  const processed = processOutput(raw)
  if (!processed.ok) return processed

  const transformed = await transformOutput(processed.value)
  if (!transformed.ok) return transformed

  const validated = await validateOutput(transformed.value, {
    computeEmbedding,
    getCosineSimilarity,
    getAttributionThreshold,
  })
  if (!validated.ok) return validated

  return storeOutput(validated.value)
}
