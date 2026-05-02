# Session Continuity Tracking — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Session Continuity Tracking

Wizard tracks three distinct session layers and links them explicitly:

| Layer                     | ID type                    | Lifetime                   | Stored in                        |
| ------------------------- | -------------------------- | -------------------------- | -------------------------------- |
| Claude Code agent session | UUID string                | Single conversation thread | `WizardSession.agent_session_id` |
| Wizard session            | Integer (SQLite PK)        | Matches agent session 1:1  | `WizardSession.id`               |
| FastMCP session           | Per-connection `ctx.state` | Transport lifetime         | Not persisted                    |

**Session directory (`settings.paths.sessions_dir/<uuid>/`):**

Each top-level agent session owns an isolated directory under the path returned by
`settings.paths.sessions_dir` (defaults to `~/.wizard/sessions/`). Sub-agents have no
directory (they're suppressed entirely).

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

**`prior_summaries` in `session_start`:**

`session_start` calls `build_prior_summaries()` (in `tools/session_helpers.py`) to
return the 3 most recent closed sessions that have summaries. Each entry includes a
`task_ids` list reconstructed from the session's serialised `SessionState.working_set`.
These are included in `SessionStartResponse.prior_summaries` so the agent can orient
itself on recent context without calling `resume_session`.

**`resume_session` also writes `wizard_id`:**

Like `session_start`, `resume_session` writes the new wizard session integer ID to
`settings.paths.sessions_dir / agent_session_id / "wizard_id"` when an
`agent_session_id` is provided. This mirrors the behaviour of `session_start` so that
`session-end.sh` can always locate the correct session ID for cleanup.

**`_is_safe_session_id()` sanitization:**

Before using `agent_session_id` as a filesystem path component, both `session_start`
and `resume_session` call `_is_safe_session_id()` (in `tools/session_tools.py`).
The check rejects empty strings, paths containing `..`, and characters in `{"/", "\\", ":"}`.
Valid inputs include standard UUIDs and agent-generated IDs like
`session-2026-04-22-gemini-studio-free-tier`. If rejected, the ID is treated as `None`
and a warning is logged.

**Key files:**

- `hooks/session-start.sh` — sub-agent suppression, keyed dir write, UUID in additionalContext
- `hooks/session-end.sh` — sub-agent suppression, keyed dir lookup, cleanup
- `tools/session_helpers.py` — `find_previous_session_id()`, `build_prior_summaries()`
- `tools/session_tools.py` — `_is_safe_session_id()`, `session_start`, `resume_session`
- `models.py` — `WizardSession.agent_session_id`, `WizardSession.continued_from_id`
- `schemas.py` — `SessionStartResponse.source`, `SessionStartResponse.prior_summaries`, `SessionStartResponse.continued_from_id`
