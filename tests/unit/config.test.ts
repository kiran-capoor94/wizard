// tests/unit/config.test.ts
import { describe, it, expect } from 'vitest'
import { parseConfig } from '../../core/config.js'

const VALID_CONFIG = `
integrations:
  notion:
    token: secret-notion-token
  jira:
    token: secret-jira-token
    project: PD
  github:
    token: secret-github-token
  krisp:
    method: mcp
ide:
  primary: neovim
security:
  pii_scrubbing: true
  encryption_at_rest: true
`

describe('parseConfig', () => {
  it('parses a valid config and returns structured data', () => {
    const config = parseConfig(VALID_CONFIG)
    expect(config.integrations.notion.token).toBe('secret-notion-token')
    expect(config.integrations.jira.token).toBe('secret-jira-token')
    expect(config.integrations.jira.project).toBe('PD')
    expect(config.integrations.github.token).toBe('secret-github-token')
    expect(config.integrations.krisp.method).toBe('mcp')
    expect(config.ide.primary).toBe('neovim')
    expect(config.security.piiScrubbing).toBe(true)
    expect(config.security.encryptionAtRest).toBe(true)
  })

  it('throws when notion token is missing', () => {
    const broken = VALID_CONFIG.replace('token: secret-notion-token', '')
    expect(() => parseConfig(broken)).toThrow()
  })

  it('throws when ide.primary is not a valid value', () => {
    const broken = VALID_CONFIG.replace('primary: neovim', 'primary: emacs')
    expect(() => parseConfig(broken)).toThrow()
  })

  it('throws when the YAML is malformed', () => {
    expect(() => parseConfig('this: is: not: valid: yaml:')).toThrow()
  })
})
