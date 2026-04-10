// tests/unit/validate.test.ts
import { describe, it, expect, vi } from 'vitest'
import { validateOutput } from '../../core/output/validate.js'
import type { ValidateDeps } from '../../core/output/validate.js'

// Hardcoded integer IDs — no database needed
const taskId = 1
const meetingId = 42

function makeDeps(overrides: Partial<ValidateDeps> = {}): ValidateDeps {
  return {
    computeEmbedding: vi.fn().mockResolvedValue({ ok: true, value: new Array(768).fill(0.1) }),
    getCosineSimilarity: vi.fn().mockResolvedValue(null),
    getAttributionThreshold: vi.fn().mockResolvedValue(0.75),
    ...overrides,
  }
}

describe('validateOutput', () => {
  it('passes schema contract for valid TransformedOutput', async () => {
    const deps = makeDeps()

    const result = await validateOutput({
      taskId,
      summary: 'Implemented auth',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(true)
  })

  it('passes attribution check when similarity is above threshold', async () => {
    const deps = makeDeps({
      getCosineSimilarity: vi.fn().mockResolvedValue(0.90),
    })

    const result = await validateOutput({
      taskId,
      summary: 'Implemented auth discussed in sprint planning',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(true)
  })

  it('rejects when similarity is below threshold (wrong attribution)', async () => {
    const deps = makeDeps({
      getCosineSimilarity: vi.fn().mockResolvedValue(0.30),
    })

    const result = await validateOutput({
      taskId,
      summary: 'Some completely unrelated work',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Attribution check failed')
    expect(result.reason).toContain('0.30')
  })

  it('skips attribution check when no meetingId is claimed', async () => {
    const deps = makeDeps()

    const result = await validateOutput({
      taskId,
      summary: 'Did some work',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(true)
    expect(deps.getCosineSimilarity).not.toHaveBeenCalled()
  })

  it('skips attribution check when task has no stored embedding', async () => {
    const deps = makeDeps({
      getCosineSimilarity: vi.fn().mockResolvedValue(null),
    })

    const result = await validateOutput({
      taskId,
      summary: 'Work done',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(true)
  })

  it('skips attribution check when embedding computation fails', async () => {
    const deps = makeDeps({
      computeEmbedding: vi.fn().mockResolvedValue({ ok: false, reason: 'Ollama unreachable' }),
    })

    const result = await validateOutput({
      taskId,
      summary: 'Work done with Ollama down',
      status: 'DONE',
      meetingId,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(true)
    expect(deps.getCosineSimilarity).not.toHaveBeenCalled()
  })

  it('rejects schema-invalid output (empty summary)', async () => {
    const deps = makeDeps()

    const result = await validateOutput({
      taskId,
      summary: '',
      status: 'DONE',
      meetingId: null,
      externalTaskId: null,
      notes: null,
    }, deps)

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Schema contract failed')
  })
})
