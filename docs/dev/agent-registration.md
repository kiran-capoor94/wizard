# Agent Registration — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Agent Registration

`wizard setup --agent <agent>` writes MCP config into the agent's config
file **and** installs the auto-capture SessionEnd hook into the agent's
global hooks config. Supported agents and their config locations:

| Agent            | MCP Config                                                        | Hook Config               | Hook Event                      |
| ---------------- | ----------------------------------------------------------------- | ------------------------- | ------------------------------- |
| `claude-code`    | `~/.claude.json`                                                  | `~/.claude/settings.json` | SessionEnd, SessionStart        |
| `claude-desktop` | `~/Library/Application Support/Claude/claude_desktop_config.json` | _(no hooks)_              | —                               |
| `gemini`         | `~/.gemini/settings.json`                                         | `~/.gemini/settings.json` | SessionEnd, SessionStart        |
| `opencode`       | `~/.config/opencode/opencode.json`                                | _(TypeScript plugin)_     | —                               |
| `codex`          | `~/.codex/config.toml`                                            | `~/.codex/hooks.json`     | Stop, SessionStart              |
| `copilot`        | `~/.copilot/mcp-config.json`                                      | `~/.copilot/config.json`  | sessionEnd, sessionStart        |

`wizard setup --agent all` registers all six (MCP) and installs hooks
where supported. `wizard update` re-registers both. `wizard uninstall`
removes both.

For agents that support `SessionStart` (codex, gemini, copilot), the hook uses
`session-start-minimal.sh` (a lightweight script that does not start a full
wizard session). `claude-code` uses the full `session-start.sh`. The
`sessionStart` event name is lowercase for copilot; all others use `SessionStart`.

## Skill installation

After hook installation, `install_skills()` copies wizard skills from the
package into each agent's native skills directory. The destination per agent:

| Agent            | Skills directory                          |
| ---------------- | ----------------------------------------- |
| `claude-code`    | `~/.claude/skills/`                       |
| `claude-desktop` | `~/.claude/skills/`                       |
| `gemini`         | `~/.gemini/skills/`                       |
| `codex`          | `~/.agents/skills/`                       |
| `opencode`       | `~/.config/opencode/skills/`              |
| `copilot`        | `~/.copilot/skills/`                      |

`install_skills()` merges — existing skills not provided by Wizard are left
untouched. `SKILL-POST.md` files are excluded from the copy.

MCP entry point:

```json
{
  "command": "wizard-server",
  "args": [],
  "type": "stdio"
}
```
