// interfaces/cli/index.ts
import { Command } from 'commander'
import { setup } from './commands/setup.js'

const program = new Command()

program
  .name('wizard')
  .description('AI-powered engineering workflow system')
  .version('0.2.0')

program
  .command('setup')
  .description('Read wizard.config.yaml and configure all integrations')
  .action(async () => {
    await setup()
  })

program.parseAsync(process.argv)
