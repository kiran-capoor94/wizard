// core/output/transform.ts
import { prisma } from '../../data/db.js'
import type { ProcessedOutput, TransformedOutput, PipelineResult } from './types.js'

/**
 * Maps a ProcessedOutput to a TransformedOutput by resolving foreign keys.
 * All IDs are int (matching Int @id @default(autoincrement()) schema).
 * Returns ok: false if taskId or meetingId do not exist in Postgres.
 */
export async function transformOutput(
  processed: ProcessedOutput
): Promise<PipelineResult<TransformedOutput>> {
  const task = await prisma.task.findUnique({ where: { id: processed.taskId } })
  if (!task) {
    return { ok: false, reason: `Task not found: ${processed.taskId}` }
  }

  if (processed.meetingId !== null) {
    const meeting = await prisma.meeting.findUnique({
      where: { id: processed.meetingId },
    })
    if (!meeting) {
      return { ok: false, reason: `Meeting not found: ${processed.meetingId}` }
    }
  }

  return {
    ok: true,
    value: {
      taskId: processed.taskId,
      summary: processed.summary,
      status: processed.status,
      meetingId: processed.meetingId,
      externalTaskId: processed.externalTaskId,
      notes: processed.notes,
    },
  }
}
