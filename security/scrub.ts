// security/scrub.ts
import { createHash } from 'node:crypto'
import type { ScrubResult, AuditEntry } from './types.js'

const PRESIDIO_ANALYZER_URL = process.env.PRESIDIO_ANALYZER_URL ?? 'http://localhost:5002'
const PRESIDIO_ANONYMIZER_URL = process.env.PRESIDIO_ANONYMIZER_URL ?? 'http://localhost:5001'

type AnalyzerResult = {
  entity_type: string
  start: number
  end: number
  score: number
}

function sha256(value: string): string {
  return createHash('sha256').update(value).digest('hex')
}

/**
 * Detects and removes PII from a text string using Microsoft Presidio.
 * Returns the cleaned text and an audit entry for each match.
 * Scrub only — detected PII is removed, not replaced.
 */
export async function scrub(text: string, fieldPath: string): Promise<ScrubResult> {
  const analyzeResponse = await fetch(`${PRESIDIO_ANALYZER_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language: 'en' }),
  })

  if (!analyzeResponse.ok) {
    throw new Error(`Presidio analyzer error: ${analyzeResponse.status}`)
  }

  const entities: AnalyzerResult[] = await analyzeResponse.json()

  const entries: AuditEntry[] = entities.map((entity) => ({
    fieldPath,
    piiType: entity.entity_type.toLowerCase(),
    originalHash: sha256(text.slice(entity.start, entity.end)),
  }))

  if (entities.length === 0) {
    return { text, entries: [] }
  }

  const anonymizeResponse = await fetch(`${PRESIDIO_ANONYMIZER_URL}/anonymize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      analyzer_results: entities,
      anonymizers: { DEFAULT: { type: 'replace', new_value: '' } },
    }),
  })

  if (!anonymizeResponse.ok) {
    throw new Error(`Presidio anonymizer error: ${anonymizeResponse.status}`)
  }

  const result = await anonymizeResponse.json()
  const cleaned = (result.text as string).replace(/  +/g, ' ').trim()

  return { text: cleaned, entries }
}
