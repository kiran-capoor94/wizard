# Agent Registration Reference

Source: `src/wizard/agent_registration.py`, `src/wizard/services.py`

---

## `_AGENTS` dict

All 6 supported agents:

| agent_id | config_path | format | mcp_key |
|----------|-------------|--------|---------|
| `claude-code` | `~/.claude.json` | `json` | `mcpServers` |
| `claude-desktop` | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows: `%APPDATA%/Claude/claude_desktop_config.json`; Linux: `~/.config/Claude/claude_desktop_config.json` | `json` | `mcpServers` |
| `gemini` | `~/.gemini/settings.json` | `json` | `mcpServers` |
| `opencode` | `~/.config/opencode/opencode.json` | `json` | `mcp` |
| `codex` | `~/.codex/config.toml` | `toml` | `mcp_servers` |
| `copilot` | `~/.copilot/mcp-config.json` | `json` | `mcpServers` |

---

## Hook scripts per agent

`_HOOK_SCRIPTS` dict maps agent → event name → script path under `~/.wizard/hooks/`:

| agent | Event name | Script |
|-------|-----------|--------|
| `claude-code` | `SessionStart` | `~/.wizard/hooks/session-start.sh` (full) |
| `claude-code` | `SessionEnd` | `~/.wizard/hooks/session-end.sh` |
| `codex` | `SessionStart` | `~/.wizard/hooks/session-start-minimal.sh` |
| `codex` | `Stop` | `~/.wizard/hooks/session-end.sh` |
| `gemini` | `SessionStart` | `~/.wizard/hooks/session-start-minimal.sh` |
| `gemini` | `SessionEnd` | `~/.wizard/hooks/session-end.sh` |
| `copilot` | `sessionStart` (lowercase) | `~/.wizard/hooks/session-start-minimal.sh` |
| `copilot` | `sessionEnd` (lowercase) | `~/.wizard/hooks/session-end.sh` |
| `claude-desktop` | — | No hooks (not in `_HOOK_SCRIPTS`) |
| `opencode` | — | No hooks (not in `_HOOK_SCRIPTS`) |

**`claude-code` gets the full `session-start.sh`; all other agents get `session-start-minimal.sh`.**

**`copilot` uses lowercase event names (`sessionStart`, `sessionEnd`) — all others use PascalCase.**

---

## Hook event names per agent (summary)

| agent | SessionStart event | SessionEnd event |
|-------|--------------------|-----------------|
| `claude-code` | `SessionStart` | `SessionEnd` |
| `codex` | `SessionStart` | `Stop` |
| `gemini` | `SessionStart` | `SessionEnd` |
| `copilot` | `sessionStart` | `sessionEnd` |
| `claude-desktop` | — | — |
| `opencode` | — | — |

---

## Hook config paths

`_HOOK_CONFIGS` maps agent → (config file, hooks key):

| agent | Hook config file | Hooks key |
|-------|-----------------|-----------|
| `claude-code` | `~/.claude/settings.json` | `hooks` |
| `codex` | `~/.codex/hooks.json` | `hooks` |
| `gemini` | `~/.gemini/settings.json` | `hooks` |
| `copilot` | `~/.copilot/config.json` | `hooks` |

Hook command format: `WIZARD_AGENT=<agent_id> bash <script_path>`, timeout `10`s (script startup only; synthesis runs detached).

---

## MCP entry format per agent

### JSON agents (claude-code, claude-desktop, gemini, codex-cli, copilot)
```json
{"command": "wizard-server", "args": [], "type": "stdio"}
```
Written at `<mcp_key>.wizard` in the agent's config file.

### opencode
```json
{"type": "local", "command": ["wizard-server"], "enabled": true}
```
Written at `mcp.wizard` in `~/.config/opencode/opencode.json`.

### codex (TOML)
```toml
[mcp_servers.wizard]
command = "wizard-server"
args = []
```
Written via `tomli_w` into `~/.codex/config.toml`.

---

## Skills installation

`install_skills(agent_id, source_dir)` copies skill directories from `~/.wizard/skills/` into each agent's native skills directory. **`SKILL-POST.md` files are never copied.**

`_AGENT_SKILLS_DIRS` maps agent → target directory:

| agent | Skills directory |
|-------|-----------------|
| `claude-code` | `~/.claude/skills/` |
| `claude-desktop` | `~/.claude/skills/` |
| `gemini` | `~/.gemini/skills/` |
| `codex` | `~/.agents/skills/` |
| `opencode` | `~/.config/opencode/skills/` |
| `copilot` | `~/.copilot/skills/` |

Install is a merge — existing skills not in `source_dir` are left untouched. Uninstall removes only wizard-managed skills (those present in `source_dir`).

---

## `~/.wizard/registered_agents.json`

JSON array of agent IDs that were successfully registered by the most recent `wizard setup` or `wizard update` call.

Example: `["claude-code", "gemini"]`

- Written by `write_registered_agents()` after `wizard setup`
- Read by `read_registered_agents()` at startup, `wizard update`, `wizard uninstall`, `wizard doctor`
- Fallback: `scan_all_registered()` inspects each agent's config file for the `wizard` key when this file is absent or empty

---

## `RegistrationService` class

`src/wizard/services.py` — handles setup, registration, and uninstallation.

### `register_agents(agent_ids: list[str]) -> list[dict]`
For each agent ID:
1. `agent_registration.register(aid)` — writes MCP entry into agent config
2. `agent_registration.register_hook(aid)` — installs hook entries (if supported)
3. `agent_registration.install_skills(aid, source)` — copies skills from `~/.wizard/skills/`

Returns list of `{"id": str, "success": bool, "parts": list[str], "error": str | None}` where `parts` lists what was installed: `"MCP"`, `"hook"`, `"skills"`.

### `deregister_agents(agent_ids: list[str]) -> list[dict]`
For each agent ID:
1. `agent_registration.deregister(aid)` — removes `wizard` key from agent config
2. `agent_registration.deregister_hook(aid)` — removes all wizard hook entries (scans by `~/.wizard/hooks/` path prefix)
3. `agent_registration.uninstall_skills(aid, source)` — removes wizard-managed skills from agent dir

Returns same result structure as `register_agents`.

### `refresh_skills(source_override=None) -> str`
Copies `src/wizard/skills/` (or `source_override`) into `~/.wizard/skills/` (full replace, then `_merge_wizard_modes()`). Called by `wizard setup` and `wizard update`.

### `refresh_hooks()` (module-level function in `agent_registration.py`)
Syncs hook scripts from installed package into `~/.wizard/hooks/`. Removes obsolete scripts no longer in the package. Called by `wizard setup` and `wizard update`.
