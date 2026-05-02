# Database Schema — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Database Schema

Seven SQLite tables via SQLModel, plus FTS5 virtual tables and a pseudonym map:

**Core tables:**

| Table           | Purpose                                                                                                                                                            |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `task`          | Tasks synced from Jira/Notion + local creates. Has `artifact_id` UUID, `workspace: str | None`, `persistence: str = "persistent"`.                                 |
| `note`          | Notes (investigation/decision/docs/learnings/failure/session_summary). Has `artifact_id`, `artifact_type`, `status`, `supersedes_note_id`, `synthesis_confidence`. |
| `meeting`       | Meetings ingested from Krisp or Notion. Has `artifact_id` UUID, `workspace: str | None`, `persistence: str = "persistent"`.                                        |
| `wizardsession` | Session records with serialised SessionState. Has `artifact_id`, `synthesis_status` (`pending`\|`complete`\|`partial_failure`).                                    |
| `toolcall`      | Append-only telemetry (tool name + timestamp per session)                                                                                                          |
| `task_state`    | Derived signals (1:1 with task): note counts, stale_days, last_touched                                                                                             |
| `meeting_tasks` | Join table linking meetings to tasks. Composite PK: `meeting_id` (FK → `meeting.id`) + `task_id` (FK → `task.id`).                                                |
| `pseudonym_map` | PII name pseudonymisation store. Columns: `original_hash` (SHA-256), `entity_type`, `fake_value`. Indexed on `original_hash`. Written by `PseudonymStore`.         |

**`MeetingTasks` join table:**

```python
class MeetingTasks(SQLModel, table=True):
    meeting_id: int = Field(foreign_key="meeting.id", primary_key=True)
    task_id: int = Field(foreign_key="task.id", primary_key=True)
```

SQLite table name: `meetingtasks`. Used by `Meeting.tasks` and `Task.meetings` relationships.

**FTS5 virtual tables** (kept in sync via INSERT/UPDATE/DELETE triggers):

| Virtual table | Indexed columns        | Source table    |
| ------------- | ---------------------- | --------------- |
| `note_fts`    | `content`, `note_type` | `note`          |
| `session_fts` | `summary`              | `wizardsession` |
| `meeting_fts` | `content`, `title`     | `meeting`       |
| `task_fts`    | `name`                 | `task`          |

FTS5 tables use `rowid = entity id` so `SearchRepository` can JOIN back to the source table for metadata. BM25 ranking is used by default — lower rank values indicate better matches.

**Artifact identity (v3):** Every `task`, `meeting`, and `wizardsession` row has a UUID `artifact_id`. Notes carry `artifact_id` + `artifact_type` (`"task"` \| `"session"` \| `"meeting"`) as a single anchor. Attribution priority: task > session > meeting.

**Note lifecycle:** `note.status` is a plain `str` (not an enum) with default `"active"`.
Valid values: `"active"`, `"superseded"`, `"contradicted"`, `"archived"`, `"invalid"`,
`"unclassified"`. Synthesis failures write `"unclassified"` notes with
`synthesis_confidence=0.0`. `"superseded"` notes are tracked via `supersedes_note_id`.
Analytics and `build_rolling_summary` exclude non-active notes from meaningful counts.

**Missing Note fields (synthesis provenance):**

| Field                     | Type           | Default | Purpose                                              |
| ------------------------- | -------------- | ------- | ---------------------------------------------------- |
| `reference_count`         | `int`          | `0`     | How many times this note has been referenced/surfaced |
| `source_note_ids`         | `str | None`   | `None`  | JSON array of note IDs this note was synthesised from |
| `synthesis_session_id`    | `int | None`   | `None`  | Wizard session that produced this note via synthesis  |
| `transcript_offset_start` | `int | None`   | `None`  | Line offset in transcript where synthesis source started |
| `transcript_offset_end`   | `int | None`   | `None`  | Line offset in transcript where synthesis source ended |

**`TaskState` additional fields:**

| Field                  | Type                 | Default | Purpose                                                      |
| ---------------------- | -------------------- | ------- | ------------------------------------------------------------ |
| `rolling_summary`      | `str | None`         | `None`  | Synthesised overview built from mental_models; updated on each note save |
| `last_status_change_at`| `datetime | None`    | `None`  | Tracks administrative activity separately from cognitive (note) activity |

**`WizardSession.closed_by` values:**

| Value    | Set by                                               |
| -------- | ---------------------------------------------------- |
| `"user"` | `session_end` tool (engineer explicitly closes)      |
| `"auto"` | `SessionCloser` background sweep (abandoned session) |
| `"hook"` | `wizard capture` CLI hook                            |
| `None`   | Session is still open or was never closed cleanly    |

**`TimestampMixin`:**

`TimestampMixin` is mixed into `Task`, `Meeting`, `WizardSession`, `Note`, and `TaskState`.
It adds:

- `created_at: datetime` — set to `datetime.now()` on insert, indexed.
- `updated_at: datetime` — set to `datetime.now()` on insert; updated on ORM-level writes
  via `sa_column_kwargs={"onupdate": datetime.datetime.now}`. **Important:** `onupdate` is
  an SQLAlchemy ORM mechanism only — raw SQL `UPDATE` statements will not refresh this field.
- `_strip_timezone` validator — Pydantic v2 with `validate_default=True` converts naive
  `datetime.now()` to a UTC-aware value. SQLite stores and returns naive datetimes only.
  The validator strips `tzinfo` so in-memory objects are always consistent with DB round-trips.

Legacy names: `wizardsession` and `toolcall` predate the snake_case
convention. Don't rename them — they match existing migrations.

New tables use snake_case (e.g. `task_state`, `meeting_tasks`, `pseudonym_map`).
