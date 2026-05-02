# Session Personalization — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Session Personalization

Wizard refreshes Claude Code's appearance and auto-boots the session skill
on every `SessionStart` event.

**How it works:**

1. A **SessionStart hook** (`hooks/session-start.sh`) fires at the start of
   every Claude Code session (installed by `wizard setup`).
2. **80% probability gate** (`$((RANDOM % 10)) -lt 8`): a Python heredoc
   queries `wizard.db`, selects an announcement based on task signals, picks
   a spinner verb pack, samples tips, and merges them into
   `~/.claude/settings.json`. Keys written: `companyAnnouncements`,
   `spinnerVerbs`, `spinnerTipsOverride`, and `statusLine` (only if absent).
3. **Always**: outputs `additionalContext` JSON instructing the agent to
   call the `wizard:session_start` MCP tool — no manual trigger needed.

**Announcement priority** (first match wins):

- Overdue tasks
- Analysis loops (`note_count > 3 and decision_count = 0`)
- Stale tasks (untouched > 14 days)
- Open task count > 20
- Generic fallback

**Spinner packs** — three themed sets (Absurdist, Stoic, Dramatic) selected
randomly each session.

**Failure isolation:** the personalization block runs with `|| true` — a
SQLite error or missing config file never blocks the session boot injection.

**Minimal hook for non-Claude agents:**

Not all agents support the full `session-start.sh` hook. Wizard ships a second hook,
`hooks/session-start-minimal.sh`, for agents that have a SessionStart hook event but
do not support the bash/python3 heredoc required for personalization.

| Agent          | Hook used                    | What it does                                       |
| -------------- | ---------------------------- | -------------------------------------------------- |
| Claude Code    | `session-start.sh`           | 80% probability gate, personalization, boot inject |
| Gemini         | `session-start-minimal.sh`   | Boot inject only (no personalization)              |
| Codex          | `session-start-minimal.sh`   | Boot inject only (no personalization)              |
| Copilot        | `session-start-minimal.sh`   | Boot inject only (no personalization)              |
| opencode       | _(no SessionStart hook)_     | No hook fires at session start                     |

The minimal script:
1. Suppresses sub-agents by checking for `agent_id` in the payload (same logic as the
   full hook, using `python3 -c` inline instead of `jq`).
2. Emits `additionalContext` instructing the agent to call `session-start` skill.
3. Does **not** write to `~/.claude/settings.json`, does **not** apply the 80% gate, and
   does **not** write to the sessions directory (no `source`/`wizard_id` file handoff).

Claude Code gets the full experience because its hook payload includes `session_id` and
`source`, enabling the keyed directory handoff. Agents using the minimal hook call
`session_start` without an `agent_session_id`, so `source` defaults to `"startup"`.

**Key files:**

- `hooks/session-start.sh` — full hook for Claude Code (bash + python3 heredoc)
- `hooks/session-start-minimal.sh` — minimal boot-inject-only hook (Gemini, Codex, Copilot)
- `agent_registration.py` — `register_hook()` / `deregister_hook()` now
  iterate `_HOOK_SCRIPTS` to install both SessionEnd and SessionStart
