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

**Key files:**

- `hooks/session-start.sh` — hook script (bash + python3 heredoc)
- `agent_registration.py` — `register_hook()` / `deregister_hook()` now
  iterate `_HOOK_SCRIPTS` to install both SessionEnd and SessionStart
