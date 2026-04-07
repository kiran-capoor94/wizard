import { prisma } from '../db.js'
import type { AuditEntry } from '../../security/types.js'

/**
 * Persists audit entries from the security layer to the AuditLog table.
 */
export async function writeAuditEntries(
  source: string,
  entries: AuditEntry[]
): Promise<void> {
  if (entries.length === 0) return
  await prisma.auditLog.createMany({
    data: entries.map((entry) => ({
      source,
      fieldPath: entry.fieldPath,
      piiType: entry.piiType,
      originalHash: entry.originalHash,
    })),
  })
}
