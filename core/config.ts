// core/config.ts
import { load as parseYaml } from 'js-yaml'
import { z } from 'zod'

const ConfigSchema = z.object({
  integrations: z.object({
    notion: z.object({ token: z.string().min(1) }),
    jira: z.object({
      token: z.string().min(1),
      project: z.string().min(1).default('PD'),
    }),
    github: z.object({ token: z.string().min(1) }),
    krisp: z.object({ method: z.literal('mcp') }),
  }),
  ide: z.object({
    primary: z.enum(['neovim', 'vscode', 'claude-desktop']),
  }),
  security: z.object({
    pii_scrubbing: z.boolean(),
    encryption_at_rest: z.boolean(),
  }),
})

export type WizardConfig = {
  integrations: {
    notion: { token: string }
    jira: { token: string; project: string }
    github: { token: string }
    krisp: { method: 'mcp' }
  }
  ide: { primary: 'neovim' | 'vscode' | 'claude-desktop' }
  security: { piiScrubbing: boolean; encryptionAtRest: boolean }
}

export function parseConfig(yaml: string): WizardConfig {
  const raw = parseYaml(yaml)
  const parsed = ConfigSchema.parse(raw)
  return {
    integrations: parsed.integrations,
    ide: parsed.ide,
    security: {
      piiScrubbing: parsed.security.pii_scrubbing,
      encryptionAtRest: parsed.security.encryption_at_rest,
    },
  }
}
