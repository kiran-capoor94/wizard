# Agent Registration — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Agent Registration

`wizard setup --agent <agent>` writes MCP config into the agent's config
file **and** installs the auto-capture SessionEnd hook into the agent's
global hooks config. Supported agents and their config locations:

| Agent            | MCP Config                                                        | Hook Config               | Hook Event               |
| ---------------- | ----------------------------------------------------------------- | ------------------------- | ------------------------ |
| `claude-code`    | `~/.claude.json`                                                  | `~/.claude/settings.json` | SessionEnd, SessionStart |
| `claude-desktop` | `~/Library/Application Support/Claude/claude_desktop_config.json` | _(no hooks)_              | —                        |
| `gemini`         | `~/.gemini/settings.json`                                         | `~/.gemini/settings.json` | SessionEnd               |
| `opencode`       | `~/.config/opencode/opencode.json`                                | _(TypeScript plugin)_     | —                        |
| `codex`          | `~/.codex/config.toml`                                            | `~/.codex/hooks.json`     | Stop                     |
| `copilot`        | `~/.copilot/mcp-config.json`                                      | `~/.copilot/config.json`  | sessionEnd               |

`wizard setup --agent all` registers all six (MCP) and installs hooks
where supported. `wizard update` re-registers both. `wizard uninstall`
removes both.

MCP entry point:

```json
{
  "command": "wizard-server",
  "args": [],
  "type": "stdio"
}
```
