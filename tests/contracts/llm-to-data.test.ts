// tests/contracts/llm-to-data.test.ts
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import { prisma } from '../../data/db.js'
import { runOutputPipeline } from '../../core/output/pipeline.js'

// computeEmbedding returns PipelineResult<EmbeddingVector> — mock the full shape
vi.mock('../../core/output/embeddings.js', () => ({
  computeEmbedding: vi.fn().mockResolvedValue({ ok: true, value: new Array(768).fill(0.1) }),
}))

// pgvector queries — use controlled similarity; storeTaskEmbedding is a no-op
vi.mock('../../data/repositories/embeddings.js', () => ({
  storeTaskEmbedding: vi.fn().mockResolvedValue(undefined),
  getCosineSimilarity: vi.fn().mockResolvedValue(null), // no stored embedding = skip attribution
  getAttributionThreshold: vi.fn().mockResolvedValue(0.75),
}))

let taskId: number

beforeAll(async () => {
  const task = await prisma.task.create({
    data: { title: 'Implement auth', status: 'IN_PROGRESS', taskType: 'CODING' },
  })
  taskId = task.id
})

afterAll(async () => {
  await prisma.workflowRun.deleteMany({ where: { taskId } })
  await prisma.task.delete({ where: { id: taskId } })
})

const validOutput = (id: number) => `
Here is my task summary.

\`\`\`json
{
  "taskId": ${id},
  "summary": "Implemented JWT authentication with RS256",
  "status": "DONE",
  "notes": "Added token refresh logic"
}
\`\`\`
`

describe('LLM → Data contract', () => {
  it('valid output is stored and retrievable from Postgres', async () => {
    const result = await runOutputPipeline(validOutput(taskId))

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error(result.reason)

    const task = await prisma.task.findUnique({ where: { id: taskId } })
    const run = await prisma.workflowRun.findUnique({
      where: { id: result.value.workflowRunId },
    })

    expect(task!.status).toBe('DONE')
    expect(run).not.toBeNull()
    expect((run!.output as Record<string, unknown>).summary).toBe('Implemented JWT authentication with RS256')
  })

  it('invalid output (no JSON block) is rejected and not stored', async () => {
    const countBefore = await prisma.workflowRun.count({ where: { taskId } })

    const result = await runOutputPipeline('I have completed the task. No JSON here.')

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('No JSON block found')

    const countAfter = await prisma.workflowRun.count({ where: { taskId } })
    expect(countAfter).toBe(countBefore)
  })

  it('output with wrong taskId is rejected at transform step', async () => {
    const result = await runOutputPipeline(validOutput(999999))

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Task not found')
  })

  it('wrong attribution is rejected when similarity is below threshold', async () => {
    const { getCosineSimilarity } = await import('../../data/repositories/embeddings.js')
    vi.mocked(getCosineSimilarity).mockResolvedValueOnce(0.20) // below 0.75

    const meeting = await prisma.meeting.create({
      data: { title: 'Unrelated meeting', keyPoints: [] },
    })

    const outputWithWrongMeeting = `\`\`\`json
{
  "taskId": ${taskId},
  "summary": "Done some work",
  "status": "DONE",
  "meetingId": ${meeting.id}
}
\`\`\``

    const result = await runOutputPipeline(outputWithWrongMeeting)

    await prisma.meeting.delete({ where: { id: meeting.id } })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Attribution check failed')
  })
})
