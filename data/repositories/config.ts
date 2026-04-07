import { prisma } from '../db.js'
import { encrypt, decrypt } from '../../security/encrypt.js'

export type IntegrationSource = 'notion' | 'jira' | 'github' | 'krisp'

/**
 * Stores an integration token (encrypted) in IntegrationConfig.
 * Upserts: safe to call multiple times for the same source.
 * Returns ok: false if encryption fails (key misconfigured).
 */
export async function storeIntegrationToken(
  source: IntegrationSource,
  token: string,
  metadata?: Record<string, unknown>
): Promise<{ ok: true } | { ok: false; reason: string }> {
  const encrypted = encrypt(token)
  if (!encrypted.ok) return encrypted

  await prisma.integrationConfig.upsert({
    where: { source },
    update: { token: encrypted.value },
    create: { source, token: encrypted.value, metadata: metadata as any },
  })
  return { ok: true }
}

/**
 * Retrieves and decrypts an integration token.
 * Returns null if not configured, ok: false if decryption fails.
 */
export async function getIntegrationToken(
  source: IntegrationSource
): Promise<string | null> {
  const config = await prisma.integrationConfig.findUnique({ where: { source } })
  if (!config) return null
  const decrypted = decrypt(config.token)
  if (!decrypted.ok) return null
  return decrypted.value
}
