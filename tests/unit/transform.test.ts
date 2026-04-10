// tests/unit/transform.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { PrismaClient } from '../../generated/prisma/client.js'
import { PrismaPg } from '@prisma/adapter-pg'
import { transformOutput } from '../../core/output/transform.js'

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

describe('transformOutput', () => {
  it('maps ProcessedOutput to TransformedOutput with resolved meeting', async () => {
    const result = await transformOutput({
      taskId,
      summary: 'Done the work',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: 'Discussed in sprint',
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return

    expect(result.value.taskId).toBe(taskId)
    expect(result.value.summary).toBe('Done the work')
    expect(result.value.status).toBe('DONE')
    expect(result.value.meetingId).toBe(meetingId)
    expect(result.value.notes).toBe('Discussed in sprint')
  })

  it('sets meetingId to null when meetingId is null', async () => {
    const result = await transformOutput({
      taskId,
      summary: 'Done the work',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.value.meetingId).toBeNull()
  })

  it('returns ok: false when taskId does not exist in Postgres', async () => {
    const result = await transformOutput({
      taskId: 999999,
      summary: 'Done',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Task not found')
  })

  it('returns ok: false when meetingId does not exist in Postgres', async () => {
    const result = await transformOutput({
      taskId,
      summary: 'Done',
      status: 'DONE',
      meetingId: 999999,
      externalTaskId: null,
      notes: null,
    })

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Meeting not found')
  })
})
