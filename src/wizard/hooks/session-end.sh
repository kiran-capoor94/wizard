#!/usr/bin/env bash
# Wizard auto-capture: reads SessionEnd hook stdin JSON, synthesises transcript.
#
# Install in agent settings:
#   Claude Code: ~/.claude/settings.json
#   Gemini: ~/.gemini/settings.json
#   Copilot: ~/.copilot/config.json
set -euo pipefail

INPUT=$(cat)

# ── Sub-agent suppression (Claude Code only) ───────────────────────────────────────────
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // empty' 2>/dev/null || true)
[ -n "$AGENT_ID" ] && exit 0

# Detect transcript path and session ID from hook input.
# Claude Code/Gemini provide transcript_path; Codex/Copilot provide session_id.
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // .transcript // empty' 2>/dev/null || true)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)

# Default agent (Claude Code for backward compat)
AGENT="${WIZARD_AGENT:-claude-code}"

if [ -z "$TRANSCRIPT" ] && [ -z "$SESSION_ID" ]; then
    exit 0
fi

# Only meaningful as a dev-checkout fallback below — a real install runs the
# `wizard` entry point directly and never touches this path.
WIZARD_DIR="$(cd "$(dirname "$0")/.." && pwd)"

ARGS=(capture --close)

[ -n "$TRANSCRIPT" ] && ARGS+=(--transcript "$TRANSCRIPT")
[ -n "$SESSION_ID" ] && ARGS+=(--agent-session-id "$SESSION_ID")
ARGS+=(--agent "$AGENT")

# Look up wizard integer session ID from keyed directory.
if [ -n "$SESSION_ID" ]; then
    WIZARD_ID_FILE="$HOME/.wizard/sessions/$SESSION_ID/wizard_id"
    if [ -f "$WIZARD_ID_FILE" ]; then
        WIZARD_SESSION_ID=$(cat "$WIZARD_ID_FILE")
        if [[ "$WIZARD_SESSION_ID" =~ ^[0-9]+$ ]]; then
            ARGS+=(--session-id "$WIZARD_SESSION_ID")
        fi
    fi
fi

# Keyed session directory — cleaned up after synthesis completes.
CLEANUP_DIR=""
[ -n "$SESSION_ID" ] && CLEANUP_DIR="$HOME/.wizard/sessions/$SESSION_ID"

# Run synthesis in background so the hook returns immediately.
# Local LLMs can take minutes; blocking the hook causes hook timeouts.
(
    LOG="$HOME/.wizard/synthesis.log"
    # `uv --directory` only makes sense against a dev checkout (needs
    # pyproject.toml there); refresh_hooks() copies this script to
    # ~/.wizard/hooks/ for real installs, where WIZARD_DIR resolves to
    # ~/.wizard and this branch would silently no-op every session. Prefer
    # the installed entry point whenever it's actually on PATH.
    if command -v wizard >/dev/null 2>&1; then
        if wizard "${ARGS[@]}" >> "$LOG" 2>&1; then
            CAPTURE_STATUS=0
        else
            CAPTURE_STATUS=$?
        fi
    elif [ -f "$WIZARD_DIR/pyproject.toml" ]; then
        if uv --directory "$WIZARD_DIR" run wizard "${ARGS[@]}" >> "$LOG" 2>&1; then
            CAPTURE_STATUS=0
        else
            CAPTURE_STATUS=$?
        fi
    else
        echo "wizard: no 'wizard' binary on PATH and no dev checkout at $WIZARD_DIR — capture skipped" >> "$LOG" 2>&1
        CAPTURE_STATUS=1
    fi
    # Only clean up the retry-linkage directory on success — on failure it
    # holds transcript_path/wizard_id needed for `wizard capture --close
    # --session-id <id>` to retry, per docs/dev/synthesis.md.
    if [ "$CAPTURE_STATUS" -eq 0 ] && [ -n "$CLEANUP_DIR" ]; then
        rm -rf "$CLEANUP_DIR" 2>/dev/null || true
    fi
) &
disown $!
