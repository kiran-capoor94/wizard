# Doctor Checks — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Doctor Checks

`wizard doctor` runs 8 checks in order. Stops at first failure unless
`--all` is passed.

| #   | Check             | What it validates                             |
| --- | ----------------- | --------------------------------------------- |
| 1   | DB file           | `settings.db` path exists                     |
| 2   | Config file       | `~/.wizard/config.json` exists                |
| 3   | DB tables         | All 6 required tables present                 |
| 4   | Allowlist file    | `~/.wizard/allowlist.txt` exists              |
| 5   | Agent registered  | ≥1 agent in registered_agents.json or scanned |
| 6   | Migration current | Alembic revision matches DB                   |
| 7   | Skills installed  | `~/.wizard/skills/` is non-empty              |
| 8   | Knowledge store   | KS type configured (INFO only)                |
