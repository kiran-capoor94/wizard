import { storeEncryptedToken, getEncryptedToken } from '../data/repositories/config.js'
import { encrypt, decrypt } from '../security/encrypt.js'

export type { IntegrationSource } from '../data/repositories/config.js'
import type { IntegrationSource } from '../data/repositories/config.js'

/**
 * Encrypts and stores an integration token. Returns ok: false if the
 * encryption key is misconfigured.
 */
export async function storeIntegrationToken(
  source: IntegrationSource,
  token: string,
  metadata?: Record<string, unknown>
): Promise<{ ok: true } | { ok: false; reason: string }> {
  const encrypted = encrypt(token)
  if (!encrypted.ok) return encrypted
  await storeEncryptedToken(source, encrypted.value, metadata)
  return { ok: true }
}

/**
 * Retrieves and decrypts an integration token.
 * Returns null if not configured or decryption fails.
 */
export async function getIntegrationToken(
  source: IntegrationSource
): Promise<string | null> {
  const encryptedToken = await getEncryptedToken(source)
  if (!encryptedToken) return null
  const decrypted = decrypt(encryptedToken)
  if (!decrypted.ok) return null
  return decrypted.value
}
