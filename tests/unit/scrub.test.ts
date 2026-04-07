// tests/unit/scrub.test.ts
import { describe, it, expect } from 'vitest'
import { scrub } from '../../security/scrub.js'

// Requires: docker compose up -d (Presidio sidecar must be running)
describe('scrub (Presidio)', () => {
  it('removes email addresses from text', async () => {
    const result = await scrub('Contact kiran@example.com for details', 'notion.meeting.notes')
    expect(result.text).not.toContain('kiran@example.com')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
    expect(result.entries[0].piiType).toContain('email')
  })

  it('removes UK phone numbers from text', async () => {
    const result = await scrub('Call +447700900123 to discuss', 'notion.task.description')
    expect(result.text).not.toContain('+447700900123')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
  })

  it('returns unchanged text when no PII is present', async () => {
    const input = 'Deploy the auth service to staging'
    const result = await scrub(input, 'notion.task.title')
    expect(result.text).toBe(input)
    expect(result.entries).toHaveLength(0)
  })

  it('stores a SHA-256 hash of the original match', async () => {
    const result = await scrub('Contact dev@example.com', 'test.field')
    if (result.entries.length > 0) {
      expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)
    }
  })
})
