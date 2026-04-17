# Design: Interactive Setup with Full Integration Configuration

**Date:** 2026-04-17  
**Status:** Approved

## Problem

`wizard setup` currently:
- Asks for only one Notion field (daily page parent ID)
- Leaves all other credentials (Notion token, database IDs, all Jira fields) to be hand-edited in `~/.wizard/config.json`
- Never runs schema discovery during setup — only via `wizard configure --notion`
- Gives almost no feedback about what it did or didn't do
- Has no Jira configuration flow at all

Users end up with an incomplete config and no clear path to fix it.

## Goal

`wizard setup` produces a fully populated config in one run. It asks which integrations the user wants, collects only the relevant credentials, runs Notion schema discovery immediately if Notion is chosen, and gives clear printed feedback at every step. Already-configured integrations are skipped with instructions to reconfigure later.

## Approach: Linear wizard (single guided flow)

One command, top-to-bottom. No new abstractions. Fits the existing imperative Typer style. Each step prints a header and a result line.

## Setup Flow

```
1. Create ~/.wizard dirs and default config
   → "Created ~/.wizard"  (silent if already exists)

2. Ask: "Which integrations would you like to configure?"
   [1] Notion
   [2] Jira
   [3] Both
   [4] Neither

3. Notion (if chosen and not yet configured)
   a. Prompt: Notion integration token
      Hint: "Find at notion.so/profile/integrations"
   b. Prompt: Daily page parent ID (optional)
      Hint: "The Notion page where daily session notes are created"
   c. Prompt: Tasks database ID
      Hint: "The data source ID of your tasks database"
   d. Prompt: Meetings database ID
      Hint: "The data source ID of your meetings database"
   e. Run schema discovery immediately
      "Discovering Notion schema..."
      Print each matched field: "  task_name → Task"
      For unmatched required fields: interactive fallback prompt (existing behaviour)
      "Schema saved."

4. Jira (if chosen and not yet configured)
   a. Prompt: Base URL    — hint: "e.g. https://yourorg.atlassian.net"
   b. Prompt: Project key — hint: "e.g. ENG"
   c. Prompt: Email
   d. Prompt: API token   — hint: "Generate at id.atlassian.com/manage-profile/security/api-tokens"

5. Already-configured integrations
   Print: "Notion already configured — run 'wizard configure --notion' to update"
   (do not re-prompt, do not overwrite)

6. Install skills         → "Installing skills...     ok"
7. Initialise database    → "Initialising database... ok"
8. Agent selection + registration (existing flow, unchanged)

9. Final summary block:
   "Setup complete.
     Notion  configured
     Jira    skipped (run 'wizard configure --jira' to add)
     Agent   claude-code"
```

## `wizard configure` updates

Add a `--jira` flag parallel to the existing `--notion`:

| Command                      | Behaviour                                      |
|------------------------------|------------------------------------------------|
| `wizard configure --notion`  | Re-prompts all Notion fields + schema discovery |
| `wizard configure --jira`    | Re-prompts all Jira fields                      |
| `wizard configure` (no flag) | Prints: "Available: --notion, --jira"           |

The Notion discovery function (`_run_notion_discovery`) is already extracted — setup calls it directly. No duplication.

## Verbose Feedback Format

Plain `typer.echo` lines throughout. No spinners, no rich formatting — works in all terminals including non-TTY.

```
Notion integration
  token:              set
  daily page ID:      set
  tasks database:     set
  meetings database:  set
  Discovering schema...
    task_name        → Task
    task_status      → Status
    task_priority    → Priority
    task_due_date    → Due date
    task_jira_key    → Jira
    meeting_title    → Meeting name
    meeting_category → Category
    meeting_date     → Date
    meeting_url      → Krisp URL
    meeting_summary  → Summary
  Schema saved.

Jira integration
  base_url:    https://acme.atlassian.net
  project_key: ENG
  email:       set
  token:       set

Installing skills...      ok
Initialising database...  ok

Agent registration
  claude-code  registered

─────────────────────────────
Setup complete.
  Notion  configured
  Jira    skipped (run 'wizard configure --jira' to add)
  Agent   claude-code
```

## Files to Change

| File | Change |
|------|--------|
| `src/wizard/cli/main.py` | Rewrite `setup()`: add integration selection, Notion credential prompts, Jira credential prompts, call `_run_notion_discovery` inline, verbose feedback, final summary |
| `src/wizard/cli/main.py` | Add `--jira` flag to `configure()` and implement `_run_jira_configure()` helper |

No other files need changing — `notion_discovery.py`, `config.py`, `integrations.py` are untouched.

## What is NOT changing

- The `--agent` flag on `setup` (existing behaviour preserved)
- The Notion schema discovery algorithm (`notion_discovery.py`)
- Database migration flow
- Skills installation
- Agent registration logic
- Config file format or location

## Success Criteria

- Running `wizard setup` on a fresh machine produces a fully populated `~/.wizard/config.json` with no manual editing required
- Running `wizard setup` on an already-configured machine skips configured integrations and prints reconfiguration hints
- Running `wizard configure --jira` reconfigures Jira credentials interactively
- Every step of setup prints meaningful output — nothing happens silently
