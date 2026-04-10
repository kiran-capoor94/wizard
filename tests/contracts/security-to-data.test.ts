// tests/contracts/security-to-data.test.ts
import { describe, it, expect, afterAll } from 'vitest'
import { PrismaClient } from '../../generated/prisma/client.js'
import { PrismaPg } from '@prisma/adapter-pg'
import { scrub } from '../../security/scrub.js'

const prisma = new PrismaClient({
  adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL! }),
})
const createdTaskIds: number[] = []
const createdMeetingIds: number[] = []
const createdActionItemIds: number[] = []

afterAll(async () => {
  for (const id of createdActionItemIds) {
    await prisma.actionItem.delete({ where: { id } }).catch(() => {})
  }
  for (const id of createdTaskIds) {
    await prisma.task.delete({ where: { id } }).catch(() => {})
  }
  for (const id of createdMeetingIds) {
    await prisma.meeting.delete({ where: { id } }).catch(() => {})
  }
  await prisma.$disconnect()
})

describe('Security → Data contract', () => {
  it('only PII-free text is written to Postgres (Task with int ID)', async () => {
    const rawTitle = 'Task for dev@example.com'
    const rawDescription = 'Contact someone to discuss'

    const [scrubbedTitle, scrubbedDescription] = await Promise.all([
      scrub(rawTitle, 'test.title'),
      scrub(rawDescription, 'test.description'),
    ])

    const task = await prisma.task.create({
      data: {
        title: scrubbedTitle.text,
        description: scrubbedDescription.text,
        status: 'TODO',
        taskType: 'INVESTIGATION',
      },
    })
    createdTaskIds.push(task.id)

    expect(typeof task.id).toBe('number')

    const stored = await prisma.task.findUnique({ where: { id: task.id } })

    expect(stored!.title).not.toContain('dev@example.com')
    expect(stored!.title).toContain('Task for')
  })

  it('ActionItem records are created separately from Meeting (not String[])', async () => {
    const rawTitle = 'Sprint planning notes'
    const rawAction = 'Follow up about deployment'

    const [scrubbedTitle, scrubbedAction] = await Promise.all([
      scrub(rawTitle, 'test.meeting.title'),
      scrub(rawAction, 'test.meeting.actionItem.0'),
    ])

    const meeting = await prisma.meeting.create({
      data: {
        title: scrubbedTitle.text,
        keyPoints: ['Discussed sprint goals'],
      },
    })
    createdMeetingIds.push(meeting.id)
    expect(typeof meeting.id).toBe('number')

    const actionItem = await prisma.actionItem.create({
      data: {
        action: scrubbedAction.text,
        meetingId: meeting.id,
      },
    })
    createdActionItemIds.push(actionItem.id)
    expect(typeof actionItem.id).toBe('number')

    const fetched = await prisma.actionItem.findUnique({
      where: { id: actionItem.id },
      include: { meeting: true },
    })
    expect(fetched!.meetingId).toBe(meeting.id)
    expect(fetched!.meeting.id).toBe(meeting.id)
  })

  it('scrub audit entries have hashed PII, not plaintext', async () => {
    const piiText = 'Contact admin@example.com'
    const result = await scrub(piiText, 'test.notes')

    expect(result.entries.length).toBeGreaterThanOrEqual(1)
    expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)

    const task = await prisma.task.create({
      data: {
        title: result.text,
        status: 'TODO',
        taskType: 'INVESTIGATION',
      },
    })
    createdTaskIds.push(task.id)

    const stored = await prisma.task.findUnique({ where: { id: task.id } })
    expect(stored!.title).not.toContain('admin@example.com')
  })

  it('Task uses externalTaskId and branch fields', async () => {
    const task = await prisma.task.create({
      data: {
        title: 'Test field names',
        status: 'TODO',
        taskType: 'CODING',
        externalTaskId: 'PD-99',
        branch: 'feature/auth-flow',
      },
    })
    createdTaskIds.push(task.id)

    const stored = await prisma.task.findUnique({ where: { id: task.id } })
    expect(stored!.externalTaskId).toBe('PD-99')
    expect(stored!.branch).toBe('feature/auth-flow')
    expect(stored!.repoId).toBeNull()
  })

  it('Task supports BLOCKED status and TaskPriority enum', async () => {
    const task = await prisma.task.create({
      data: {
        title: 'Blocked task',
        status: 'BLOCKED',
        priority: 'HIGH',
        taskType: 'DEBUGGING',
      },
    })
    createdTaskIds.push(task.id)

    const stored = await prisma.task.findUnique({ where: { id: task.id } })
    expect(stored!.status).toBe('BLOCKED')
    expect(stored!.priority).toBe('HIGH')
  })
})
