# Database Schema — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Database Schema

Seven SQLite tables via SQLModel, plus FTS5 virtual tables and a pseudonym map:

**Core tables:**

| Table           | Purpose                                                                                                                                                               |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task`          | Tasks synced from Jira/Notion + local creates. Has `artifact_id` UUID.                                                                                                |
| `note`          | Notes (investigation/decision/docs/learnings/failure/session_summary). Has `artifact_id`, `artifact_type`, `status`, `supersedes_note_id`, `synthesis_confidence`.    |
| `meeting`       | Meetings ingested from Krisp or Notion. Has `artifact_id` UUID.                                                                                                       |
| `wizardsession` | Session records with serialised SessionState. Has `artifact_id`, `synthesis_status` (`pending`\|`complete`\|`partial_failure`).                                       |
| `toolcall`      | Append-only telemetry (tool name + timestamp per session)                                                                                                             |
| `task_state`    | Derived signals (1:1 with task): note counts, stale_days, last_touched                                                                                                |
| `pseudonym_map` | PII name pseudonymisation store. Columns: `original_hash` (SHA-256), `entity_type`, `fake_value`. Indexed on `original_hash`. Written by `PseudonymStore`.            |

**FTS5 virtual tables** (kept in sync via INSERT/UPDATE/DELETE triggers):

| Virtual table  | Indexed columns          | Source table    |
| -------------- | ------------------------ | --------------- |
| `note_fts`     | `content`, `note_type`   | `note`          |
| `session_fts`  | `summary`                | `wizardsession` |
| `meeting_fts`  | `content`, `title`       | `meeting`       |
| `task_fts`     | `name`                   | `task`          |

FTS5 tables use `rowid = entity id` so `SearchRepository` can JOIN back to the source table for metadata. BM25 ranking is used by default — lower rank values indicate better matches.

**Artifact identity (v3):** Every `task`, `meeting`, and `wizardsession` row has a UUID `artifact_id`. Notes carry `artifact_id` + `artifact_type` (`"task"` \| `"session"` \| `"meeting"`) as a single anchor. Attribution priority: task > session > meeting.

**Note lifecycle:** `note.status` is `"active"` by default. Synthesis failures write `"unclassified"` notes with `synthesis_confidence=0.0`. `"superseded"` notes are tracked via `supersedes_note_id`. Analytics and `build_rolling_summary` exclude non-active notes from meaningful counts.

Legacy names: `wizardsession` and `toolcall` predate the snake_case
convention. Don't rename them — they match existing migrations.

New tables use snake_case (e.g. `task_state`, `meeting_tasks`, `pseudonym_map`).
