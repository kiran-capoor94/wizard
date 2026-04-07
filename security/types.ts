// security/types.ts
import type { AuditEntry } from '../shared/types.js'

export type { AuditEntry }

export type ScrubResult = {
  text: string           // cleaned text with PII removed
  entries: AuditEntry[]  // one entry per detected PII instance
}
