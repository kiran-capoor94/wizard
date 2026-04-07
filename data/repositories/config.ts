import { prisma } from '../db.js'
import { Prisma } from '../../generated/prisma/client.js'

export type IntegrationSource = 'notion' | 'jira' | 'github' | 'krisp'

/**
 * Stores a pre-encrypted token in IntegrationConfig.
 * Callers are responsible for encrypting before passing.
 */
export async function storeEncryptedToken(
  source: IntegrationSource,
  encryptedToken: string,
  metadata?: Record<string, unknown>
): Promise<void> {
  await prisma.integrationConfig.upsert({
    where: { source },
    update: { token: encryptedToken, metadata: (metadata ?? {}) as Prisma.InputJsonObject },
    create: { source, token: encryptedToken, metadata: (metadata ?? {}) as Prisma.InputJsonObject },
  })
}

/**
 * Returns the raw (encrypted) token string, or null if not configured.
 */
export async function getEncryptedToken(
  source: IntegrationSource
): Promise<string | null> {
  const config = await prisma.integrationConfig.findUnique({ where: { source } })
  return config?.token ?? null
}
