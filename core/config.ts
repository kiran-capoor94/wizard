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
  security: z
    .object({
      pii_scrubbing: z.boolean(),
      encryption_at_rest: z.boolean(),
    })
    .transform((s) => ({
      piiScrubbing: s.pii_scrubbing,
      encryptionAtRest: s.encryption_at_rest,
    })),
})

export type WizardConfig = z.infer<typeof ConfigSchema>

export function parseConfig(yaml: string): WizardConfig {
  const raw = parseYaml(yaml)
  return ConfigSchema.parse(raw)
}
