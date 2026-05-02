# synthesis.md — transcript synthesis reference

Sources: `src/wizard/synthesis.py`, `src/wizard/synthesis_prompt.py`, `src/wizard/llm_adapters.py`, `src/wizard/mid_session.py`, `src/wizard/transcript.py`

---

## `Synthesiser` class

`src/wizard/synthesis.py`

### Constructor args

| Arg | Type | Default | Notes |
|-----|------|---------|-------|
| `reader` | `TranscriptReader` | required | Reads agent transcript files |
| `note_repo` | `NoteRepository` | required | Persists `Note` rows |
| `security` | `SecurityService` | required | PII scrubbing before save |
| `settings` | `Settings` | required | Synthesis config (backends, context_chars) |
| `task_state_repo` | `TaskStateRepository \| None` | `TaskStateRepository()` | Rolling summary recompute |
| `t_repo` | `TaskRepository \| None` | `TaskRepository()` | Open-task table fetch |
| `backend` | `dict \| None` | first healthy backend | Override backend selection |

`_chunk_char_limit = min(settings.synthesis.context_chars, 15000)`

### Key methods

| Method | Description |
|--------|-------------|
| `synthesise(db, wizard_session)` | Entry point for terminal synthesis; delegates to `synthesise_path` using `session.transcript_path` |
| `synthesise_path(db, wizard_session, transcript_path, terminal=True)` | Core implementation; calls `generate_notes` then `persist` |
| `synthesise_lines(db, wizard_session, lines)` | Mid-session partial synthesis; writes lines to a temp file then calls `synthesise_path(terminal=False)` |
| `generate_notes(transcript_path, agent, task_table)` | LLM call outside any DB transaction; returns `list[SynthesisNote]` |
| `persist(db, notes_data, wizard_session, valid_task_ids, terminal, had_failure)` | Saves notes, updates session state, refreshes rolling summaries |
| `prepare_task_table(db)` | Returns `(task_table_str, valid_task_ids_set)` for prompt construction |
| `write_failure_marker(db, wizard_session, chunk_description)` | Writes a recoverable `NoteType.INVESTIGATION` note on synthesis failure |

---

## Pipeline: `synthesise(session_id)` flow

```
synthesise(db, wizard_session)
  └─ synthesise_path(db, wizard_session, Path(transcript_path), terminal=True)
       ├─ prepare_task_table(db)              → (task_table, valid_task_ids)
       ├─ generate_notes(path, agent, task_table)
       │    ├─ _read_entries()                → list[TranscriptEntry]
       │    ├─ filter_for_synthesis(entries)  → filtered entries
       │    ├─ format_prompt(filtered, task_table) → user message
       │    └─ _call_adapter(messages, filtered, task_table)
       │         ├─ llm_complete(...)          → list[SynthesisNote]  [attempt 1]
       │         ├─ retry on non-context error [attempt 2]
       │         └─ ContextWindowExceededError → _synthesise_in_chunks()
       │              └─ splits by _chunk_char_limit (min(context_chars, 15000) chars)
       │                 llm_complete per chunk, no per-chunk retry
       └─ persist(db, notes_data, wizard_session, valid_task_ids, terminal=True)
            ├─ _save_notes()                  validates task_id against valid_task_ids
            ├─ session.synthesis_status = "complete" | "partial_failure"
            ├─ session.is_synthesised = True  (only on full success)
            └─ _refresh_rolling_summaries()   → recompute TaskState for touched tasks
```

**On `generate_notes` failure**: `write_failure_marker` saves a recoverable investigation note; `persist` is called with `had_failure=True` → `synthesis_status = "partial_failure"`.

---

## `synthesis_prompt.py`

### `filter_for_synthesis(entries)`

Drops low-signal entries and truncates content per role:

- **`tool_call`**: always kept; content truncated to `ROLE_CHAR_LIMITS["tool_call"]` (150 chars)
- **`tool_result`**: kept **only** if the originating tool call name is in `KEEP_RESULT_TOOLS`; truncated to 200 chars
- **other roles** (`user`, `assistant`): kept; truncated to `ROLE_CHAR_LIMITS.get(role, 2000)`

```python
KEEP_RESULT_TOOLS = frozenset({"Edit", "Write", "Agent", "Bash"})
```

### `ROLE_CHAR_LIMITS`

| Role | Char limit |
|------|-----------|
| `user` | 400 |
| `assistant` | 400 |
| `tool_call` | 150 |
| `tool_result` | 200 |

Default for unknown roles: 2000.

### `format_prompt(filtered, task_table)`

- Safety trim: if total content chars > 15,000 after filtering, drops oldest entries from the front until under the limit.
- Appends open-tasks table (`id<TAB>name`) or `"task_id must always be null"` when no tasks are available.
- Appends note type definitions and JSON schema instruction (`CRITICAL: Respond ONLY with a valid JSON array`).

### `format_transcript(entries)`

Each entry → `[role] content` or `[role:tool_name] content`, one line per entry.

---

## Task matching

- LLM receives open-tasks table (`id<TAB>name`) in the prompt.
- LLM returns `task_id` per `SynthesisNote` object.
- **`_save_notes()` validates** each `task_id` against `valid_task_ids` set; unrecognised IDs → `task_id = None` (note anchors to session instead).
- **The LLM does task matching; wizard validates the result.**

---

## Mid-session synthesis

`mid_session_synthesis_loop()` is defined in `src/wizard/tools/session_helpers.py`.

- Polls every **300 seconds** (default `interval_seconds=300`).
- **Enabled when**: `settings.synthesis.enabled=True` AND `agent_session_id` is present in `session_start`.
- **Launched by** `session_start` — creates an `asyncio.Task` and registers it via `register_mid_session_task(agent_session_id, task)`.
- **Cancelled by** `session_end` — calls `cancel_mid_session_synthesis(agent_session_id)`.
- Uses `synthesise_lines()` (`terminal=False`) — does not mark session as synthesised.
- On poll failure: logs at DEBUG, retries next interval. `session_end` synthesis is the guaranteed full-synthesis path.

### `MID_SESSION_TASKS` (`mid_session.py`)

```python
MID_SESSION_TASKS: dict[str, asyncio.Task[None]] = {}
```

- Keyed by `agent_session_id`.
- `register_mid_session_task`: cancels any existing task for the key before inserting; guarded by `asyncio.Lock`.
- `cancel_mid_session_synthesis`: `dict.pop()` + `task.cancel()`; no lock needed (atomic under asyncio's single-threaded model).

---

## LLM adapters (`llm_adapters.py`)

Two backends, selected by model name:

| Condition | Backend | Notes |
|-----------|---------|-------|
| `"ollama"` in model name (case-insensitive) | `OllamaAdapter` | Native `/api/chat`; bypasses LiteLLM; `think: false`; no grammar constraint; `parse_notes` for robust JSON extraction |
| All other models | `litellm.completion` | Cloud: `timeout=90`, `max_tokens=1024`; local non-Ollama: `stream=False`, `timeout=300`, `extra_body={"enable_thinking": False}` |

`probe_backend_health(base_url)`: only probes local backends (`localhost`/`127.0.0.1`) via `GET /v1/models`; cloud APIs return `True` unconditionally.

**Backend selection**: `Synthesiser._select_backend` iterates `synthesis.backends` in config order; returns the first backend where `probe_backend_health` returns `True`. Falls back to top-level `synthesis.model/base_url/api_key` if none pass health check.

`OllamaAdapter` options: `num_predict=2048`, `temperature=0.1`. `num_ctx` and `num_thread` are deliberately omitted to avoid forcing model re-initialisation on every call.

---

## `TranscriptReader` (`transcript.py`)

### `find_transcript(agent_session_id, agent="claude-code")`

Agent-specific discovery:

| Agent | Discovery method |
|-------|-----------------|
| `claude-code` | `~/.claude/projects/*/<uuid>.jsonl` glob |
| `copilot` | `~/.copilot/session-state/<id>/events.jsonl` |
| `codex` | Returns `None` — date-sharded; hook must provide path via `--transcript` |
| `gemini` | Returns `None` — requires `transcript_path` from hook |
| `opencode` | Path constructed inside `_read_opencode`; uses `~/.local/share/opencode/storage/message/<session_id>/` |

### `read_new_lines(path, skip)`

Incremental read for mid-session polling:
- Reads all lines, returns `lines[skip:]`.
- **Drops the last new line** (`new[:-1]`) to guard against partial JSON objects while the file is being written.
- Dropped line is picked up on the next poll once the following line has been written.

### Supported formats

| Agent | Format | Parser method |
|-------|--------|---------------|
| `claude-code` | JSONL with `type: user/assistant` entries and content blocks | `_read_claude_code` |
| `codex` | JSONL with `type: response_item`, `payload.type: message/function_call/function_call_output` | `_read_codex` |
| `gemini` | JSONL with `type: user/gemini`, `toolCalls` array | `_read_gemini` |
| `opencode` | JSON files in `~/.local/share/opencode/storage/message/<session_id>/`, sorted by creation time | `_read_opencode` |
| `copilot` | JSONL with `type: user.message/assistant.message/tool.execution_complete` | `_read_copilot` |

---

## `synthesis_status` values

| Value | Set when |
|-------|----------|
| `"pending"` | Session created; synthesis not yet run |
| `"complete"` | `persist()` called with `terminal=True` and no chunk failures |
| `"partial_failure"` | `persist()` called with `terminal=True` and `had_failure=True` |

---

## Retry command

```bash
wizard capture --close --session-id <id>
```

Re-runs synthesis for a session with `synthesis_status = "partial_failure"`. Failure marker note content includes this command.
