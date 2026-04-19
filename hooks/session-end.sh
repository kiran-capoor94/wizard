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

if [ -z "$TRANSCRIPT" ]; then
    exit 0
fi

WIZARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_ID_FILE="$HOME/.wizard/current_session_id"

ARGS=(capture --close --transcript "$TRANSCRIPT" --agent claude-code)
if [ -f "$SESSION_ID_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_ID_FILE")
    if [[ "$SESSION_ID" =~ ^[0-9]+$ ]]; then
        ARGS+=(--session-id "$SESSION_ID")
    fi
fi

uv --directory "$WIZARD_DIR" run wizard "${ARGS[@]}" 2>/dev/null || true
