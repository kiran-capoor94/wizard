import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto'

const ALGORITHM = 'aes-256-gcm'
const IV_LENGTH = 12
const TAG_LENGTH = 16

export type EncryptResult =
  | { ok: true; value: string }
  | { ok: false; reason: string }

function getKey(): Buffer | null {
  const hex = process.env.WIZARD_ENCRYPTION_KEY
  if (!hex || hex.length !== 64) return null
  return Buffer.from(hex, 'hex')
}

/**
 * Encrypts a plaintext string using AES-256-GCM.
 * Returns ok: false if WIZARD_ENCRYPTION_KEY is missing or malformed.
 */
export function encrypt(plaintext: string): EncryptResult {
  const key = getKey()
  if (!key) {
    return { ok: false, reason: 'WIZARD_ENCRYPTION_KEY must be a 64-character hex string (32 bytes)' }
  }
  const iv = randomBytes(IV_LENGTH)
  const cipher = createCipheriv(ALGORITHM, key, iv)

  const encrypted = Buffer.concat([
    cipher.update(plaintext, 'utf8'),
    cipher.final(),
  ])
  const tag = cipher.getAuthTag()

  return { ok: true, value: Buffer.concat([iv, tag, encrypted]).toString('base64') }
}

/**
 * Decrypts a base64-encoded AES-256-GCM ciphertext.
 * Returns ok: false if the key is missing or the ciphertext is malformed/corrupted.
 */
export function decrypt(ciphertext: string): EncryptResult {
  const key = getKey()
  if (!key) {
    return { ok: false, reason: 'WIZARD_ENCRYPTION_KEY must be a 64-character hex string (32 bytes)' }
  }
  try {
    const data = Buffer.from(ciphertext, 'base64')

    const iv = data.subarray(0, IV_LENGTH)
    const tag = data.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH)
    const encrypted = data.subarray(IV_LENGTH + TAG_LENGTH)

    const decipher = createDecipheriv(ALGORITHM, key, iv)
    decipher.setAuthTag(tag)

    return { ok: true, value: Buffer.concat([decipher.update(encrypted), decipher.final()]).toString('utf8') }
  } catch (err) {
    return { ok: false, reason: `Decryption failed: ${String(err)}` }
  }
}
