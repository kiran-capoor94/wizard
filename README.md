# Wizard

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built with FastMCP](https://img.shields.io/badge/built%20with-FastMCP-purple)](https://github.com/jlowin/fastmcp)
[![SQLite](https://img.shields.io/badge/database-SQLite-lightblue)](https://www.sqlite.org/)

*A local memory layer for AI agents. Syncs Jira and Notion, scrubs PII, and surfaces structured context across sessions.*

AI coding agents forget everything between sessions. Wizard gives them persistent memory — tasks, meetings, notes, and decisions — synced from the tools you already use, with PII scrubbed before anything touches disk.

## Quick Start

**Prerequisites:** Python 3.14+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/kiran-capoor94/wizard.git
cd wizard
uv sync
wizard setup
```

`wizard setup` creates `~/.wizard/`, scaffolds `config.json`, installs skills, and registers the MCP server with Claude Code and Claude Desktop.

See [Configuration](#configuration) for Jira and Notion setup.
