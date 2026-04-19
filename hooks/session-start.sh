#!/usr/bin/env bash
# Wizard SessionStart hook: personalization refresh (80%) + session boot injection (always).
#
# Registered by: wizard setup / wizard update
# Claude Code event: SessionStart
set -euo pipefail

SETTINGS="$HOME/.claude/settings.json"
DB="$HOME/.wizard/wizard.db"

# ── Step 1: Personalization refresh (80% gate) ────────────────────────────────
if [ $((RANDOM % 10)) -lt 8 ]; then
    python3 - "$SETTINGS" "$DB" <<'PYEOF' 2>/dev/null || true
import json
import random
import sqlite3
import sys
from datetime import datetime, UTC
from pathlib import Path

settings_path = Path(sys.argv[1])
db_path = Path(sys.argv[2])

if not settings_path.exists() or not db_path.exists():
    sys.exit(0)

try:
    data = json.loads(settings_path.read_text())
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

# ── Query task signals ────────────────────────────────────────────────────────
try:
    conn = sqlite3.connect(str(db_path))
    now = datetime.now(UTC).isoformat()

    overdue_row = conn.execute(
        "SELECT COUNT(*), MIN(name) FROM task "
        "WHERE due_date IS NOT NULL AND due_date < ? "
        "AND status NOT IN ('done', 'archived')",
        (now,),
    ).fetchone()

    loop_row = conn.execute(
        "SELECT COUNT(*), t.name, ts.note_count "
        "FROM task t JOIN task_state ts ON t.id = ts.task_id "
        "WHERE ts.note_count > 3 AND ts.decision_count = 0 "
        "AND t.status NOT IN ('done', 'archived') "
        "LIMIT 1",
    ).fetchone()

    stale_row = conn.execute(
        "SELECT MAX(ts.stale_days), t.name "
        "FROM task t JOIN task_state ts ON t.id = ts.task_id "
        "WHERE ts.stale_days > 14 AND t.status NOT IN ('done', 'archived')",
    ).fetchone()

    open_count = conn.execute(
        "SELECT COUNT(*) FROM task WHERE status IN ('todo', 'in_progress', 'blocked')",
    ).fetchone()[0]

    conn.close()
except Exception:
    sys.exit(0)

# ── Pick announcement (first matching signal wins) ────────────────────────────
overdue_count = overdue_row[0] or 0
overdue_name = overdue_row[1] or ""
loop_count = loop_row[0] or 0
loop_name = loop_row[1] or ""
loop_notes = loop_row[2] or 0
stale_days = stale_row[0] or 0
stale_name = stale_row[1] or ""

if overdue_count:
    msg = (
        f"You have {overdue_count} task(s) that were due before now. "
        "Time is a construct. Deadlines, unfortunately, are not."
    )
elif loop_count:
    msg = (
        f"'{loop_name}' has {loop_notes} investigation notes and 0 decisions. "
        "You are very thorough at not deciding."
    )
elif stale_days > 14:
    msg = f"'{stale_name}' hasn't been touched in {stale_days} days. It's developed feelings."
elif open_count > 20:
    msg = f"{open_count} open tasks. You're not procrastinating — you're portfolio managing."
else:
    msg = "No disasters detected. Check back in 5 minutes."

# ── Pick spinner verb pack (rotate between 3) ─────────────────────────────────
packs = [
    ["Summoning focus", "Pretending to know", "Asking nicely", "Overthinking this"],
    ["Sitting with uncertainty", "Accepting the complexity tax", "Breathing through the stack trace"],
    ["Staring into the void", "Arguing with past-you", "Negotiating with entropy"],
]
verbs = random.choice(packs)

# ── Sample 4 tips from pool of 10 ────────────────────────────────────────────
tips_pool = [
    "That task you've been 'about to start' for two weeks? Still there. Still judging.",
    "A blocked task is just a task with commitment issues.",
    "If you've reopened this task three times, it's not a task. It's a hobby.",
    "Every note you save is future-you saying thank you. Future-you is easily impressed.",
    "Scope creep: when a task refuses to respect its own boundaries.",
    "Closing a task: the adult version of finishing your vegetables.",
    "A task with no notes is a mystery wrapped in a title.",
    "Estimation is just optimism with a deadline attached.",
    "The best time to write a note was during the work. The second best time is now.",
    "Blocked by: future-you, who refuses to exist yet.",
]
tips = random.sample(tips_pool, 4)

# ── Merge into settings.json ──────────────────────────────────────────────────
data["companyAnnouncements"] = [msg]
data["spinnerVerbs"] = {"mode": "replace", "verbs": verbs}
data["spinnerTipsOverride"] = {"tips": tips, "excludeDefault": True}

if "statusLine" not in data:
    status_cmd = (
        "sqlite3 ~/.wizard/wizard.db "
        "\"SELECT COUNT(*) FROM task WHERE status IN ('todo','in_progress','blocked')\" "
        "2>/dev/null | awk '{print \"\U0001F9D9 \" $1 \" tasks | \" ENVIRON[\"MODEL_NAME\"]}'"
    )
    data["statusLine"] = {"type": "command", "command": status_cmd}

settings_path.write_text(json.dumps(data, indent=2))
PYEOF
fi

# ── Step 2: Session boot injection (always) ───────────────────────────────────
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"Begin this session by invoking the wizard:session-start skill."}}'
