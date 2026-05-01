# Session Continuity Tracking — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Session Continuity Tracking

Wizard tracks three distinct session layers and links them explicitly:

| Layer                     | ID type                    | Lifetime                   | Stored in                        |
| ------------------------- | -------------------------- | -------------------------- | -------------------------------- |
| Claude Code agent session | UUID string                | Single conversation thread | `WizardSession.agent_session_id` |
| Wizard session            | Integer (SQLite PK)        | Matches agent session 1:1  | `WizardSession.id`               |
| FastMCP session           | Per-connection `ctx.state` | Transport lifetime         | Not persisted                    |

**Session directory (`~/.wizard/sessions/<uuid>/`):**

Each top-level agent session owns an isolated directory. Sub-agents have no directory (they're suppressed entirely).

| File        | Written by                              | Read by                             | Content                                 |
| ----------- | --------------------------------------- | ----------------------------------- | --------------------------------------- |
| `source`    | `session-start.sh` hook at SessionStart | `session_start` tool                | `"startup"`, `"compact"`, or `"resume"` |
| `wizard_id` | `session_start` tool after DB insert    | `session-end.sh` hook at SessionEnd | Integer wizard session ID               |

The directory is deleted by `session-end.sh` after `wizard capture` completes.

**Sub-agent suppression:**

Both `session-start.sh` and `session-end.sh` exit immediately (`exit 0`) when `agent_id` is present in the hook payload. Top-level sessions never have `agent_id` — this is the suppression signal from Claude Code.

**Continuation detection (`session_start` tool):**

1. The `SessionStart` hook writes `source` (from payload) to `~/.wizard/sessions/<uuid>/source`.
2. The hook emits `agent_session_id=<uuid> source=<source>` in `additionalContext`.
3. The agent calls `session_start(agent_session_id=<uuid>)`.
4. `session_start` reads `source` from the keyed directory.
5. If `source == "compact"`, the tool queries the DB for the most recent prior session and sets `continued_from_id`.

**Key files:**

- `hooks/session-start.sh` — sub-agent suppression, keyed dir write, UUID in additionalContext
- `hooks/session-end.sh` — sub-agent suppression, keyed dir lookup, cleanup
- `tools/session_tools.py` — `SESSIONS_DIR`, `_find_previous_session_id`, `agent_session_id` param
- `models.py` — `WizardSession.agent_session_id`, `WizardSession.continued_from_id`
- `schemas.py` — `SessionStartResponse.source`, `SessionStartResponse.continued_from_id`
