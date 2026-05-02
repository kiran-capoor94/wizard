# Commands reference

All wizard commands are run via the `wizard` CLI. Install with `uv tool install wizard`, then run `wizard --help` to confirm it's on your PATH.

---

## `wizard setup`

Creates `~/.wizard/`, initialises the database, installs skills and hooks, and registers wizard as an MCP server with your agent.

**When to use:** once after installing wizard, and again after upgrading if `wizard update` isn't available yet.

**Flags:**

| Flag | Description |
|---|---|
| `--agent <id>` | Agent to register: `claude-code`, `claude-desktop`, `gemini`, `opencode`, `codex`, `copilot`, `all`. Prompted interactively if omitted. |

**Example:**

```bash
wizard setup --agent claude-code
```

---

## `wizard uninstall`

Removes all wizard runtime state (database, config, skills) and deregisters wizard from your agent's MCP config.

**When to use:** when you want to remove wizard completely. This is destructive — it deletes your notes and session history.

**Flags:**

| Flag | Description |
|---|---|
| `--yes` | Skip the confirmation prompt |

**Example:**

```bash
wizard uninstall
```

After running this, you can remove the package itself with `uv tool uninstall wizard`.

---

## `wizard doctor`

Checks that your wizard installation is healthy. Runs 8 checks covering the database, config file, migrations, agent registration, skills, and knowledge store.

**When to use:** when something seems wrong, before filing a bug report, or after a system change. Run this first — it tells you exactly what to fix.

**Flags:**

| Flag | Description |
|---|---|
| `--all` | Run all checks and report each result, instead of stopping at the first failure |

**Example:**

```bash
wizard doctor
wizard doctor --all
```

See [troubleshooting.md](troubleshooting.md) for what each check tests.

---

## `wizard verify`

Performs a live MCP handshake with `wizard-server` to confirm that the tools are actually reachable from your agent. This goes further than `doctor` — it launches the server process and sends real JSON-RPC messages.

**When to use:** when `wizard doctor` passes but the tools aren't appearing in your agent, or after setup on a new machine.

**Example:**

```bash
wizard verify
```

---

## `wizard capture`

Re-runs synthesis for a session. Currently only `--close` mode is supported, which re-runs synthesis for a session that previously failed or was skipped.

**When to use:** when a session's synthesis failed (check `wizard analytics` for `partial_failure` status) or when you want to force synthesis for a specific session.

**Flags:**

| Flag | Description |
|---|---|
| `--close` | Required. Runs synthesis for the target session. |
| `--session-id <id>` | Wizard DB session ID to target. If omitted, finds the most recent unsynthesised session within the last 24 hours. |
| `--agent-session-id <id>` | Agent-assigned session UUID, if known. |
| `--transcript <path>` | Path to a transcript file, if the agent doesn't store it in the default location. |

**Example:**

```bash
wizard capture --close --session-id 42
```

---

## `wizard configure synthesis`

Manages the LLM backends used for synthesis. Lists, adds, removes, reorders, and tests backends interactively.

**When to use:** when setting up synthesis for the first time, or when switching between local and cloud models.

**Sub-commands:**

```bash
wizard configure synthesis           # list configured backends
wizard configure synthesis add       # add a new backend (interactive)
wizard configure synthesis remove 2  # remove backend at position 2
wizard configure synthesis move 2 1  # move backend 2 to position 1 (highest priority)
wizard configure synthesis test      # test all backends
wizard configure synthesis test 1    # test only backend at position 1
```

---

## `wizard configure knowledge-store`

Configures where session summaries are written after each session ends. Supports Notion and Obsidian; defaults to local-only if not configured.

**When to use:** if you want session summaries pushed to your Notion workspace or Obsidian vault automatically.

**Example:**

```bash
wizard configure knowledge-store
```

This runs an interactive prompt asking for your knowledge store type and the relevant IDs or paths.

---

## `wizard analytics`

Shows usage statistics for sessions, notes, and tasks over a date range. Useful for checking synthesis health (look for `partial_failure` sessions) and understanding how wizard is being used.

**When to use:** to get a quick picture of recent activity, or to diagnose why synthesis might not be producing notes.

**Flags:**

| Flag | Description |
|---|---|
| `--day` | Today only |
| `--week` | Last 7 days (default) |
| `--month` | Last 30 days |
| `--from <YYYY-MM-DD>` | Custom start date |
| `--to <YYYY-MM-DD>` | Custom end date |

**Example:**

```bash
wizard analytics --week
wizard analytics --from 2026-04-01 --to 2026-04-30
```

---

## `wizard update`

Upgrades wizard to the latest version, runs pending database migrations, and re-registers your agents with the updated skills and hooks.

**When to use:** whenever a new version of wizard is available. This is the single command to run — it handles everything.

**Example:**

```bash
wizard update
```

For dev installs (editable), this also runs `git pull` and `uv sync` in the repo before re-registering.
