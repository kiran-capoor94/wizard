# Doctor Checks — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Doctor Checks

`wizard doctor` runs 9 checks in order. Stops at first failure unless
`--all` is passed.

| #   | Check             | What it validates                             |
| --- | ----------------- | --------------------------------------------- |
| 1   | DB file           | `settings.db` path exists                     |
| 2   | Config file       | `~/.wizard/config.json` exists                |
| 3   | DB tables         | All 7 required tables present                 |
| 4   | DB size           | Database file ≤200 MB; suggests `wizard vacuum` if exceeded |
| 5   | Allowlist file    | `~/.wizard/allowlist.txt` exists              |
| 6   | Agent registered  | ≥1 agent in registered_agents.json or scanned |
| 7   | Migration current | DB's stamped revision equals the bundled head |
| 8   | Skills installed  | `~/.wizard/skills/` is non-empty              |
| 9   | Knowledge store   | KS type configured (INFO only)                |

**Required tables (check #3):** `task`, `note`, `meeting`, `wizardsession`,
`toolcall`, `task_state`, `pseudonym_map`.

**Migration current (check #7):** compares the revision stamped in
`alembic_version` against the head of the bundled migration chain, and fails with
both revisions plus `run 'wizard migrate'` when they differ. It previously
reported whatever stamp it found as a PASS without comparing it to anything, so a
database several revisions behind — or wedged part-way through a failed
migration — still produced a 10/10 green report.

**Allowlist file (check #4):** This check always returns `True` — it is
advisory only. A missing allowlist is reported as a warning message but does
not fail the check or block subsequent checks. Run `wizard setup` to create
the file.

---

> **Related:** `wizard verify` runs these same checks plus an actual MCP
> handshake subprocess test. See `docs/dev/verify.md`.
