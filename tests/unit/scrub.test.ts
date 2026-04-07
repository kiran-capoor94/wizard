// tests/unit/scrub.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { scrub } from '../../security/scrub.js'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function mockAnalyzeResponse(entities: object[]) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(entities),
  } as Response)
}

function mockAnonymizeResponse(text: string) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ text }),
  } as Response)
}

beforeEach(() => {
  mockFetch.mockReset()
})

describe('scrub (Presidio)', () => {
  it('removes email addresses from text', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([{ entity_type: 'EMAIL_ADDRESS', start: 8, end: 25, score: 0.99 }]),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ text: 'Contact  for details' }),
      } as Response)

    const result = await scrub('Contact kiran@example.com for details', 'notion.meeting.notes')
    expect(result.text).not.toContain('kiran@example.com')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
    expect(result.entries[0].piiType).toContain('email')
  })

  it('removes UK phone numbers from text', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([{ entity_type: 'PHONE_NUMBER', start: 5, end: 18, score: 0.95 }]),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ text: 'Call  to discuss' }),
      } as Response)

    const result = await scrub('Call +447700900123 to discuss', 'notion.task.description')
    expect(result.text).not.toContain('+447700900123')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
  })

  it('returns unchanged text when no PII is present', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([]),
    } as Response)

    const input = 'Deploy the auth service to staging'
    const result = await scrub(input, 'notion.task.title')
    expect(result.text).toBe(input)
    expect(result.entries).toHaveLength(0)
  })

  it('stores a SHA-256 hash of the original match', async () => {
    const email = 'dev@example.com'
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([{ entity_type: 'EMAIL_ADDRESS', start: 8, end: 8 + email.length, score: 0.99 }]),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ text: 'Contact ' }),
      } as Response)

    const result = await scrub(`Contact ${email}`, 'test.field')
    expect(result.entries.length).toBeGreaterThanOrEqual(1)
    expect(result.entries[0].originalHash).toMatch(/^[a-f0-9]{64}$/)
  })
})
