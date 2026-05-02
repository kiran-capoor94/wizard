# Auto-Capture (Transcript Synthesis) — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Auto-Capture (Transcript Synthesis)

Wizard automatically generates structured notes from agent conversation
transcripts. This removes the need for manual `save_note` calls — tasks
accumulate context as you work.

**How it works:**

1. A **SessionEnd hook** fires when the agent's session ends (installed by
   `wizard setup`).
2. The hook calls `wizard capture --close --transcript <path> --agent <id> --agent-session-id <uuid> --session-id <id>`.
3. `wizard capture` finds the wizard session matching `--session-id` (written
   by `session_start`) or the most recent unsynthesised session within 24h,
   sets `transcript_path`, `agent`, and `agent_session_id`, then calls
   `Synthesiser` which routes to `OllamaAdapter` (native `/api/chat`, no
   grammar constraint, `think:false`) for Ollama backends, or to LiteLLM for
   cloud providers, and saves the resulting notes to SQLite.
   On success, `WizardSession.is_synthesised` is set to `True`.
   Raw transcript JSONL is persisted to `wizardsession.transcript_raw` before
   synthesis so re-synthesis remains possible after the agent deletes the file.
   On successful synthesis `transcript_raw` is set to `NULL` immediately to keep
   the database compact. Run `wizard vacuum` to reclaim space from older sessions
   or after a partial failure where the blob was not cleared.

**Synthesis is fully decoupled from the MCP server.** It runs at hook time,
before the next session starts. No `ctx.sample()` involved — no round-trip
cost, no dependency on MCP context availability.

**Mid-session synthesis:** `mid_session_synthesis_loop()` in
`tools/session_helpers.py` runs as a background asyncio task when
`synthesis.enabled=True` and an `agent_session_id` is present. It polls the
transcript file every 5 minutes and calls `Synthesiser.synthesise_lines()` on
new lines since the last pass. The task is launched by `session_start` and
cancelled at `session_end` (or when `SessionCloser` auto-closes the session)
via `cancel_mid_session_synthesis()`. Active task handles are stored in the
`MID_SESSION_TASKS` dict in `mid_session.py`.

**Fallback:** If the LLM server is unreachable, `wizard capture` exits non-zero.
The session retains its `transcript_path` (`is_synthesised` stays `False`). Retry
with `wizard capture --close --session-id <id>` when the server is available.

**Chunking fallback:** On `ContextWindowExceededError`, the synthesiser splits
pre-filtered entries into chunks bounded by `min(context_chars, 15000)` chars
and synthesises each chunk independently.

**Key files:**

- `transcript.py` — `TranscriptReader` (JSONL parser)
- `synthesis.py` — `Synthesiser` (backend selection + note persistence)
- `synthesis_prompt.py` — `filter_for_synthesis()` (drops low-signal entries, truncates by `ROLE_CHAR_LIMITS`), `format_prompt()` (builds LLM prompt string), `KEEP_RESULT_TOOLS` (tool results retained), `ROLE_CHAR_LIMITS` (per-role char budgets)
- `llm_adapters.py` — `OllamaAdapter` (native `/api/chat` for Ollama, bypasses LiteLLM), `LiteLLMAdapter`-style `complete()` for cloud/local non-Ollama backends, `probe_backend_health()`, JSON parsing
- `mid_session.py` — `MID_SESSION_TASKS` dict + `cancel_mid_session_synthesis()` / `register_mid_session_task()`
- `tools/session_helpers.py` — `mid_session_synthesis_loop()` (background polling loop)
- `hooks/session-end.sh` — Claude Code hook script
- `agent_registration.py` — `register_hook()` / `deregister_hook()`
- `config.py` — `SynthesisSettings` + `BackendConfig` (ordered backends list)

**`WIZARD_AGENT` environment variable:** `session-end.sh` uses this to
identify the agent type when building the `wizard capture` command. It is
set in the hook command registered by `register_hook()` at setup time
(e.g. `WIZARD_AGENT=gemini bash /path/to/session-end.sh`). Valid values
match `TranscriptReader._PARSERS`: `claude-code`, `codex`, `gemini`,
`opencode`, `copilot`. Defaults to `claude-code` if unset.

**Transcript format:** Claude Code writes JSONL with `type` field
(`user`, `assistant`, `progress`, `file-history-snapshot`, `system`,
`last-prompt`). The reader skips noise types and normalises
`tool_use`/`tool_result` blocks into `TranscriptEntry` objects.

**Note types extracted by synthesis:**

| Type            | What it captures                                                                                     |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `investigation` | Findings, observations, discovered behaviour                                                         |
| `decision`      | Choices made, rationale, trade-offs considered                                                        |
| `docs`          | How something works — protocol, API contract, architectural fact                                      |
| `learnings`     | Surprises, things that differed from expectation, updated mental models                               |
| `failure`       | Failed approaches, dead ends, incorrect assumptions, approaches that were tried and rejected          |

`failure` notes are surfaced by `task_start` ahead of other note types so the agent knows what not to retry. They are also included in synthesis deduplication by content hash.

**Task matching:** The LLM receives the open-tasks table (id + name) in the
prompt and returns a `task_id` per note. `_save_notes()` validates the returned
`task_id` against `valid_task_ids` (fetched from `prepare_task_table()`); IDs
not in the set are set to `None` and the note is anchored to the session instead.

**`synthesis_status` values:** `"pending"` | `"complete"` | `"partial_failure"`

**Limitations:**

- Transcript file must exist at synthesis time; if deleted, falls back to `wizardsession.transcript_raw` (persisted at capture time, cleared after successful synthesis)
- Parsers: Claude Code (full), Codex, Gemini, OpenCode, Copilot CLI
- Ollama backends require a running Ollama server; cloud backends require a valid API key
