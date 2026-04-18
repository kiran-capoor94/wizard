#!/usr/bin/env bash
# Wizard auto-capture: reads Claude Code SessionEnd stdin JSON and marks
# the wizard session for transcript synthesis.
#
# Install in Claude Code settings.json or plugin hooks.json:
#   "SessionEnd": [{"hooks": [{"type": "command",
#     "command": "bash /path/to/wizard/hooks/session-end.sh", "timeout": 10}]}]

set -euo pipefail

INPUT=$(cat)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)

if [ -z "$TRANSCRIPT" ]; then
    exit 0
fi

ARGS=(capture --close --transcript "$TRANSCRIPT" --agent claude-code)
if [ -n "$SESSION_ID" ]; then
    ARGS+=(--session-id "$SESSION_ID")
fi

WIZARD_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
uv --directory "$WIZARD_DIR" run wizard "${ARGS[@]}" 2>/dev/null || true
