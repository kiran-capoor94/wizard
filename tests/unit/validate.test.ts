// tests/unit/validate.test.ts
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import { PrismaClient } from '../../generated/prisma/client.js'
import { PrismaPg } from '@prisma/adapter-pg'
import { validateOutput } from '../../core/output/validate.js'

// Mock embedding and similarity so tests don't call Ollama or pgvector
vi.mock('../../data/repositories/embeddings.js', () => ({
  getCosineSimilarity: vi.fn(),
  getAttributionThreshold: vi.fn().mockResolvedValue(0.75),
}))

import { getCosineSimilarity } from '../../data/repositories/embeddings.js'

const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL! }) })
let taskId: number
let meetingId: number

beforeAll(async () => {
  const meeting = await prisma.meeting.create({
    data: { title: 'Sprint Planning', keyPoints: [] },
  })
  meetingId = meeting.id

  const task = await prisma.task.create({
    data: { title: 'Implement auth', status: 'IN_PROGRESS', taskType: 'CODING' },
  })
  taskId = task.id
})

afterAll(async () => {
  await prisma.task.delete({ where: { id: taskId } })
  await prisma.meeting.delete({ where: { id: meetingId } })
  await prisma.$disconnect()
})

describe('validateOutput', () => {
  it('passes schema contract for valid TransformedOutput', async () => {
    vi.mocked(getCosineSimilarity).mockResolvedValue(null)

    const result = await validateOutput({
      taskId,
      summary: 'Implemented auth',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(true)
  })

  it('passes attribution check when similarity is above threshold', async () => {
    vi.mocked(getCosineSimilarity).mockResolvedValue(0.90)

    const result = await validateOutput({
      taskId,
      summary: 'Implemented auth discussed in sprint planning',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(true)
  })

  it('rejects when similarity is below threshold (wrong attribution)', async () => {
    vi.mocked(getCosineSimilarity).mockResolvedValue(0.30)

    const result = await validateOutput({
      taskId,
      summary: 'Some completely unrelated work',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Attribution check failed')
    expect(result.reason).toContain('0.30')
  })

  it('skips attribution check when no meetingId is claimed', async () => {
    vi.mocked(getCosineSimilarity).mockClear()

    const result = await validateOutput({
      taskId,
      summary: 'Did some work',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(true)
    expect(getCosineSimilarity).not.toHaveBeenCalled()
  })

  it('skips attribution check when task has no stored embedding', async () => {
    vi.mocked(getCosineSimilarity).mockResolvedValue(null)

    const result = await validateOutput({
      taskId,
      summary: 'Work done',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(true)
  })
})
