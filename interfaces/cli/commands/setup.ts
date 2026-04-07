// interfaces/cli/commands/setup.ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { parseConfig } from '../../../core/config.js'
import { storeIntegrationToken } from '../../../services/integration.js'

/**
 * Reads wizard.config.yaml, stores integration tokens (encrypted), and
 * validates each connection. Prints status for each integration.
 */
export async function setup(): Promise<void> {
  const configPath = join(process.cwd(), 'wizard.config.yaml')
  let raw: string

  try {
    raw = readFileSync(configPath, 'utf-8')
  } catch {
    console.error('wizard.config.yaml not found. Copy wizard.config.example.yaml and fill in your tokens.')
    process.exit(1)
  }

  const config = parseConfig(raw)
  console.log('Config parsed. Storing integration tokens...')

  // Notion
  const notionResult = await storeIntegrationToken('notion', config.integrations.notion.token)
  if (!notionResult.ok) {
    console.error(`Notion token storage failed: ${notionResult.reason}`)
    process.exit(1)
  }
  console.log('✓ Notion: token stored')

  // Jira
  const jiraResult = await storeIntegrationToken('jira', config.integrations.jira.token, {
    project: config.integrations.jira.project,
  })
  if (!jiraResult.ok) {
    console.error(`Jira token storage failed: ${jiraResult.reason}`)
    process.exit(1)
  }
  console.log('✓ Jira: token stored')

  // GitHub
  const githubResult = await storeIntegrationToken('github', config.integrations.github.token)
  if (!githubResult.ok) {
    console.error(`GitHub token storage failed: ${githubResult.reason}`)
    process.exit(1)
  }
  console.log('✓ GitHub: token stored')

  console.log('\nSetup complete. Run `wizard doctor` to verify all connections.')
}
