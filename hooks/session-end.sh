#!/usr/bin/env bash
# Wizard auto-capture: reads Claude Code SessionEnd stdin JSON, synthesises transcript.
#
# Install in Claude Code settings.json:
#   "SessionEnd": [{"hooks": [{"type": "command",
#     "command": "bash /path/to/wizard/hooks/session-end.sh", "timeout": 10}]}]
set -euo pipefail

INPUT=$(cat)

# ── Sub-agent suppression ─────────────────────────────────────────────────────
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty' 2>/dev/null || true)
[ -n "$AGENT_ID" ] && exit 0

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
AGENT_UUID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)

if [ -z "$TRANSCRIPT" ]; then
    exit 0
fi

WIZARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"

ARGS=(capture --close --transcript "$TRANSCRIPT" --agent claude-code)

# Look up wizard integer session ID from the keyed directory.
if [ -n "$AGENT_UUID" ]; then
    WIZARD_ID_FILE="$HOME/.wizard/sessions/$AGENT_UUID/wizard_id"
    if [ -f "$WIZARD_ID_FILE" ]; then
        WIZARD_SESSION_ID=$(cat "$WIZARD_ID_FILE")
        if [[ "$WIZARD_SESSION_ID" =~ ^[0-9]+$ ]]; then
            ARGS+=(--session-id "$WIZARD_SESSION_ID")
        fi
    fi
    ARGS+=(--agent-session-id "$AGENT_UUID")
fi

uv --directory "$WIZARD_DIR" run wizard "${ARGS[@]}" 2>/dev/null || true

# Clean up the keyed session directory now that capture is complete.
if [ -n "$AGENT_UUID" ]; then
    rm -rf "$HOME/.wizard/sessions/$AGENT_UUID" 2>/dev/null || true
fi
