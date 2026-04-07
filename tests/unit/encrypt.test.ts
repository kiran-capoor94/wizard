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
    const enc = encrypt(original)
    expect(enc.ok).toBe(true)
    if (!enc.ok) return
    const dec = decrypt(enc.value)
    expect(dec.ok).toBe(true)
    if (!dec.ok) return
    expect(dec.value).toBe(original)
  })

  it('produces different ciphertext for the same input each time (random IV)', () => {
    const token = 'same-token'
    const c1 = encrypt(token)
    const c2 = encrypt(token)
    expect(c1.ok).toBe(true)
    expect(c2.ok).toBe(true)
    if (!c1.ok || !c2.ok) return
    expect(c1.value).not.toBe(c2.value)
    expect(decrypt(c1.value)).toMatchObject({ ok: true, value: token })
    expect(decrypt(c2.value)).toMatchObject({ ok: true, value: token })
  })

  it('ciphertext is a non-empty string', () => {
    const result = encrypt('any-token')
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(typeof result.value).toBe('string')
    expect(result.value.length).toBeGreaterThan(0)
  })

  it('returns ok: false for corrupted ciphertext', () => {
    const result = decrypt('corrupted-ciphertext')
    expect(result.ok).toBe(false)
  })
})
