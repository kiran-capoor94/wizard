# Session Start — Post-Call Guidance

State the session ID, then surface the top recommendation and 2–3 alternatives:

**Session {session_id} started.**

**Recommendation:** {highest-priority task — id, name, why (stale_days, note_count, due_date)}

Also worth looking at:
- **{id}** — {name} ({reason})
- **{id}** — {name} ({reason})

Priority order for recommendation: overdue > blocked+stale > critical > highest priority open.
For blocked tasks, note stale_days and whether it's an analysis loop (note_count > 3, decision_count == 0).
If no open tasks, say so.

## Active Mode

If `active_mode` is set in the `session_start` response, invoke the Skill tool with that skill name before doing anything else.
