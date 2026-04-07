// tests/unit/notion-pull.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock security/scrub so the test does not call Presidio
vi.mock('../../security/scrub.js', () => ({
  scrub: vi.fn().mockImplementation(async (text: string, fieldPath: string) => ({
    text: text.replace(/[\w.+-]+@[\w.-]+\.\w+/g, '').trim(),
    entries: /[\w.+-]+@[\w.-]+\.\w+/.test(text)
      ? [{ fieldPath, piiType: 'email', originalHash: 'a'.repeat(64) }]
      : [],
  })),
}))

// Mock the Notion client before importing the module under test
vi.mock('@notionhq/client', () => ({
  Client: vi.fn().mockImplementation(() => ({
    databases: {
      query: vi.fn().mockResolvedValue({
        results: [
          {
            id: 'page-001',
            properties: {
              Name: {
                type: 'title',
                title: [{ plain_text: 'Deploy auth service' }],
              },
              Description: {
                type: 'rich_text',
                rich_text: [
                  { plain_text: 'Contact dev@example.com for access' },
                ],
              },
              Status: { type: 'select', select: { name: 'In Progress' } },
              'Due Date': {
                type: 'date',
                date: { start: '2026-04-10' },
              },
              Ticket: {
                type: 'rich_text',
                rich_text: [{ plain_text: 'PD-42' }],
              },
            },
          },
        ],
      }),
    },
  })),
}))

import { pullNotionTasks } from '../../integrations/notion/pull.js'

describe('pullNotionTasks', () => {
  it('returns tasks with scrubbed text fields', async () => {
    const tasks = await pullNotionTasks('mock-token', 'mock-db-id')

    expect(tasks).toHaveLength(1)
    expect(tasks[0].notionId).toBe('page-001')
    expect(tasks[0].title.text).toBe('Deploy auth service')
    expect(tasks[0].status).toBe('In Progress')
    expect(tasks[0].dueDate).toBe('2026-04-10')
    expect(tasks[0].externalTaskId).toBe('PD-42')
  })

  it('scrubs email addresses from description', async () => {
    const tasks = await pullNotionTasks('mock-token', 'mock-db-id')

    expect(tasks[0].description.text).not.toContain('dev@example.com')
    expect(tasks[0].description.entries).toHaveLength(1)
    expect(tasks[0].description.entries[0].piiType).toBe('email')
  })
})
