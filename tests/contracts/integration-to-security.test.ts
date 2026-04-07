// tests/contracts/integration-to-security.test.ts
import { describe, it, expect } from 'vitest'
import { scrub } from '../../security/scrub.js'
import { writeAuditEntries } from '../../data/repositories/audit.js'
import { PrismaClient } from '../../generated/prisma/client.js'
import { PrismaPg } from '@prisma/adapter-pg'

const prisma = new PrismaClient({
  adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL! }),
})

describe('Integration → Security contract', () => {
  it('raw text containing PII exits the security layer with PII removed', async () => {
    const raw = 'Discuss with alice@nhs.net about care plan'
    const result = await scrub(raw, 'notion.meeting.test.notes')

    expect(result.text).not.toContain('alice@nhs.net')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
  })

  it('audit entries are written to Postgres after scrubbing', async () => {
    const raw = 'Contact dev@example.com for access'
    const result = await scrub(raw, 'notion.task.contract-test.description')

    await writeAuditEntries('notion', result.entries)

    const logs = await prisma.auditLog.findMany({
      where: { fieldPath: 'notion.task.contract-test.description' },
    })

    expect(logs.length).toBeGreaterThanOrEqual(1)
    expect(logs[0].piiType).toBe('email_address')
    expect(logs[0].source).toBe('notion')
    expect(typeof logs[0].id).toBe('number')
    expect(logs[0].originalHash).toMatch(/^[a-f0-9]{64}$/)

    // Cleanup
    await prisma.auditLog.deleteMany({
      where: { fieldPath: 'notion.task.contract-test.description' },
    })
    await prisma.$disconnect()
  })
})
