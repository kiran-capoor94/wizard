import { describe, it, expect, beforeAll } from 'vitest'
import { encrypt, decrypt } from '../../security/encrypt.js'

beforeAll(() => {
  if (!process.env.WIZARD_ENCRYPTION_KEY) {
    throw new Error('WIZARD_ENCRYPTION_KEY must be set in .env to run encrypt tests')
  }
})

describe('encrypt / decrypt', () => {
  it('round-trips a token through encryption and decryption', () => {
    const original = 'secret-notion-token-abc123'
    const ciphertext = encrypt(original)
    const plaintext = decrypt(ciphertext)
    expect(plaintext).toBe(original)
  })

  it('produces different ciphertext for the same input each time (random IV)', () => {
    const token = 'same-token'
    const c1 = encrypt(token)
    const c2 = encrypt(token)
    expect(c1).not.toBe(c2)
    expect(decrypt(c1)).toBe(token)
    expect(decrypt(c2)).toBe(token)
  })

  it('ciphertext is a non-empty string', () => {
    const result = encrypt('any-token')
    expect(typeof result).toBe('string')
    expect(result.length).toBeGreaterThan(0)
  })

  it('throws when ciphertext is corrupted', () => {
    expect(() => decrypt('corrupted-ciphertext')).toThrow()
  })
})
