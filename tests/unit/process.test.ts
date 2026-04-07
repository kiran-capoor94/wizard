import { describe, it, expect } from 'vitest'
import { processOutput } from '../../core/output/process.js'

const VALID_OUTPUT = `
I have reviewed the task and completed the work.

\`\`\`json
{
  "taskId": 42,
  "summary": "Implemented JWT authentication middleware",
  "status": "DONE",
  "meetingId": 7,
  "notes": "Used RS256 algorithm as agreed in sprint planning"
}
\`\`\`
`

const VALID_OUTPUT_NO_MEETING = `
\`\`\`json
{
  "taskId": 42,
  "summary": "Fixed the null pointer bug",
  "status": "DONE"
}
\`\`\`
`

describe('processOutput', () => {
  it('extracts the JSON block from valid LLM output', () => {
    const result = processOutput(VALID_OUTPUT)

    expect(result.ok).toBe(true)
    if (!result.ok) return

    expect(result.value.taskId).toBe(42)
    expect(result.value.summary).toBe('Implemented JWT authentication middleware')
    expect(result.value.status).toBe('DONE')
    expect(result.value.meetingId).toBe(7)
    expect(result.value.notes).toBe('Used RS256 algorithm as agreed in sprint planning')
  })

  it('handles output without meetingId or notes', () => {
    const result = processOutput(VALID_OUTPUT_NO_MEETING)

    expect(result.ok).toBe(true)
    if (!result.ok) return

    expect(result.value.meetingId).toBeNull()
    expect(result.value.notes).toBeNull()
  })

  it('returns ok: false when no JSON block is present', () => {
    const result = processOutput('I have completed the task. Nothing else.')
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('No JSON block found')
  })

  it('returns ok: false when JSON is malformed', () => {
    const result = processOutput('```json\n{ invalid json }\n```')
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('Failed to parse JSON')
  })

  it('returns ok: false when required fields are missing', () => {
    const result = processOutput('```json\n{"summary": "done"}\n```')
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.reason).toContain('taskId')
  })

  it('returns ok: false when status is not a valid TaskStatus', () => {
    const result = processOutput(
      '```json\n{"taskId": 1, "summary": "y", "status": "INVALID"}\n```'
    )
    expect(result.ok).toBe(false)
  })
})
