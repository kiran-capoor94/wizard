#!/usr/bin/env bash
# Wizard stop hook: captures last assistant message as OBSERVATION note.
#
# Install in agent settings:
#   Claude Code: ~/.claude/settings.json → hooks.Stop
set -euo pipefail

cat | wizard hook stop || true
