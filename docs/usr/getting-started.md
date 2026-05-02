# Getting started with Wizard

Wizard is a local memory layer for AI coding agents. It runs as an MCP server alongside your agent, automatically tracking what you work on, what decisions you make, and what you learned — so your next session picks up where the last one left off.

## Prerequisites

- Python 3.11 or later
- [`uv`](https://docs.astral.sh/uv/) installed

## Install

```bash
uv tool install wizard
```

If you're working from the repo (development):

```bash
uv tool install --editable .
```

## First-time setup

Run the setup command once after installing:

```bash
wizard setup
```

This does five things:

1. Creates `~/.wizard/` with a default `config.json`
2. Copies skill files to `~/.wizard/skills/`
3. Installs hook scripts to `~/.wizard/hooks/`
4. Initialises the local SQLite database
5. Registers wizard as an MCP server in your agent's config

You'll be prompted to choose which agent to register wizard with. The default is `claude-code`. If you use multiple agents, run `wizard setup --agent all` or repeat setup for each one.

## Verify the installation

```bash
wizard verify
```

This confirms that the config and database are present, and performs a live MCP handshake with `wizard-server` to confirm the tools are reachable. If anything is wrong, it will tell you exactly which step failed.

## Your first session

Open Claude Code. Wizard tools appear automatically — no extra steps required. The `SessionStart` hook fires at the start of every conversation and calls `wizard:session_start` for you. You'll see your open tasks, any blocked items, and summaries from your last few sessions surface in the agent's context.

You don't need to do anything to start using wizard. Just open your agent and begin working.

## What wizard does automatically

Wizard handles several things without you needing to ask:

- **Session start**: the `SessionStart` hook calls `wizard:session_start` before your first message, loading your task list and prior context.
- **Mid-session synthesis**: if synthesis is enabled, wizard reads your conversation transcript every 5 minutes and extracts structured notes in the background.
- **Terminal synthesis**: when you end a session, wizard runs a full synthesis pass on the complete transcript.
- **Staleness tracking**: task staleness (days since last note) is refreshed automatically at every session start.
- **Abandoned session cleanup**: if a previous session wasn't cleanly ended, wizard detects it and auto-closes it with a synthetic summary so the context isn't lost.

## What you control

- **Ending sessions cleanly**: always end a session by calling `wizard:session_end` with a summary. This saves your intent and open threads for the next session.
- **Creating and updating tasks**: use `wizard:create_task`, `wizard:update_task`, and `wizard:task_start` to manage what you're working on.
- **Saving notes**: call `wizard:save_note` during a session to record findings, decisions, or anything worth keeping. Synthesis also saves notes automatically, but manual notes are immediate.
- **Configuration**: edit `~/.wizard/config.json` to enable synthesis, add PII allowlist entries, or point wizard at a different LLM backend. See [configuration.md](configuration.md).

## Next steps

- [Configuration](configuration.md) — enable synthesis, adjust PII scrubbing
- [Sessions](sessions.md) — how sessions work and how to end them cleanly
- [Tasks](tasks.md) — how to track and prioritise your work
- [Commands](commands.md) — full CLI reference
