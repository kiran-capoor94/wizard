// core/output/store.ts
import { prisma } from '../../data/db.js'
import { storeTaskEmbedding } from '../../data/repositories/embeddings.js'
import { computeEmbedding } from './embeddings.js'
import type { TransformedOutput, PipelineResult } from './types.js'

/**
 * Writes a validated TransformedOutput to Postgres in a single transaction.
 * Updates task status, creates a WorkflowRun record with the summary.
 * Triggers pgvector sync (vector(768) via nomic-embed-text/Ollama) after successful write.
 * pgvector sync failure is non-fatal — logged and skipped, write succeeds.
 * Rolls back on any Postgres failure — partial writes never reach the database.
 */
export async function storeOutput(
  output: TransformedOutput
): Promise<PipelineResult<{ workflowRunId: number }>> {
  let workflowRunId: number

  try {
    const result = await prisma.$transaction(async (tx) => {
      await tx.task.update({
        where: { id: output.taskId },
        data: {
          status: output.status,
          meetingId: output.meetingId,
        },
      })

      return tx.workflowRun.create({
        data: {
          workflowId: 'task_end',
          taskId: output.taskId,
          status: 'COMPLETED',
          output: {
            summary: output.summary,
            externalTaskId: output.externalTaskId,
            notes: output.notes,
          },
          completedAt: new Date(),
        },
      })
    })

    workflowRunId = result.id
  } catch (err) {
    return { ok: false, reason: `Store failed: ${String(err)}` }
  }

  // pgvector sync after successful write (outside transaction — non-fatal)
  const embResult = await computeEmbedding(output.summary)
  if (embResult.ok) {
    try {
      await storeTaskEmbedding(output.taskId, embResult.value)
    } catch (err) {
      console.warn(`pgvector sync failed for task ${output.taskId}:`, err)
    }
  }

  return { ok: true, value: { workflowRunId } }
}
