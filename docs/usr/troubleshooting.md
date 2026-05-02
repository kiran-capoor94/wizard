# Troubleshooting

## Start here: `wizard doctor`

When something isn't working, run `wizard doctor` first. It checks 8 things in order:

| Check | What it tests |
|---|---|
| Database file | The database exists at the expected path |
| Config file | `~/.wizard/config.json` exists |
| Database tables | All 7 required tables are present and schema is intact |
| Allowlist file | `~/.wizard/allowlist.txt` exists (advisory — won't fail if absent) |
| Agent registered | At least one agent has wizard registered in its MCP config |
| Migration current | The database schema is up to date with the current wizard version |
| Skills installed | Wizard skill files are present in the agent's environment |
| Knowledge store | A knowledge store is configured (advisory — wizard works without one) |

Run `wizard doctor --all` to see every result instead of stopping at the first failure.

## If `doctor` passes but MCP isn't working

Run `wizard verify`. This goes further — it launches `wizard-server` as a subprocess, sends a real JSON-RPC handshake, and confirms that the tools list is returned correctly. If `verify` fails where `doctor` passes, the problem is likely in the agent's MCP configuration or the server binary.

```bash
wizard verify
```

## Common issues

### "wizard-server not found in PATH"

The `wizard-server` binary isn't on your PATH. This usually means the `uv tool install` didn't complete correctly, or the tool's bin directory isn't in PATH.

**Fix:** Re-run setup:

```bash
uv tool install wizard
wizard setup
```

If `wizard` itself isn't found, check that `uv`'s tool bin directory is in your PATH. Run `uv tool dir` to find where tools are installed, and add it to your shell profile.

### Synthesis produces no notes

This is the most common issue after initial setup. Check these in order:

1. **Is synthesis enabled?** Open `~/.wizard/config.json` and confirm `synthesis.enabled` is `true`.

2. **Is the LLM running?** For Ollama:
   ```bash
   curl http://localhost:11434
   ```
   If this fails, start Ollama with `ollama serve`.

3. **Is the model correct?** The model string in your config must include the provider prefix — `ollama/gemma4:latest-64k`, not just `gemma4:latest-64k`.

4. **Check session synthesis status:**
   ```bash
   wizard analytics
   ```
   Sessions with `synthesis_status = "partial_failure"` tried to run synthesis but failed. Sessions still showing `pending` didn't run synthesis at all.

5. **Retry a failed session:**
   ```bash
   wizard capture --close --session-id <id>
   ```

See [synthesis.md](synthesis.md) for more on how synthesis works and how to configure it.

### "No module named wizard"

The wizard package isn't in the Python environment being used.

**Fix:** Reinstall:

```bash
uv tool install wizard
```

### Tools not appearing in Claude Code

If you open Claude Code and the `wizard:` tools don't appear, the MCP server isn't registered correctly.

1. Run `wizard verify` — if this fails, the problem is with the server itself.
2. Check that `~/.claude.json` (or `~/.claude/settings.json`) contains an `mcpServers` entry for `wizard`.
3. If the entry is missing, re-run `wizard setup --agent claude-code`.

After re-running setup, restart Claude Code completely — MCP servers are loaded at startup.

### Database locked errors

If you see errors like "database is locked" or SQLite busy errors, there may be multiple `wizard-server` processes running simultaneously.

**Check:**

```bash
ps aux | grep wizard-server
```

If you see more than one process, kill the extras:

```bash
pkill -f wizard-server
```

Then reopen your agent. Multiple server processes can happen if Claude Code is launched multiple times without the previous instance closing cleanly.

## How to check synthesis status

```bash
wizard analytics
```

This shows a breakdown of recent sessions including their synthesis status. For a specific session, look at the output from `wizard analytics --day` or `wizard analytics --week`.

## How to retry failed synthesis

```bash
wizard capture --close --session-id <id>
```

Get the session ID from `wizard analytics` — it's shown in the sessions table. This command re-runs the full synthesis pipeline for the target session. It's safe to run multiple times.
