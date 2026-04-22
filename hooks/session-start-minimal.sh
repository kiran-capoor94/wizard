#!/usr/bin/env bash
# Wizard minimal SessionStart hook.
# Emits additionalContext to force-trigger the session-start skill.
# Used by Gemini, Codex, and Copilot — no personalization logic.
# Personalization remains Claude Code-specific (hooks/session-start.sh).
#
# Registered by: wizard setup / wizard update
set -euo pipefail

INPUT=$(cat)

# Sub-agent suppression: exit silently if agent_id is present in payload.
# Top-level sessions never have agent_id — this is the suppression signal.
AGENT_ID=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent_id',''))" 2>/dev/null || true)
[ -n "$AGENT_ID" ] && exit 0

echo '{"additionalContext": "Invoke the session-start skill now to open your wizard session."}'
