// security/types.ts
export type AuditEntry = {
  fieldPath: string
  piiType: string        // Presidio entity_type, lowercased
  originalHash: string   // SHA-256 hex of the original match
}

export type ScrubResult = {
  text: string           // cleaned text with PII removed
  entries: AuditEntry[]  // one entry per detected PII instance
}
