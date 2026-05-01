# Auto-Capture (Transcript Synthesis) — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Auto-Capture (Transcript Synthesis)

Wizard automatically generates structured notes from agent conversation
transcripts. This removes the need for manual `save_note` calls — tasks
accumulate context as you work.

**How it works:**

1. A **SessionEnd hook** fires when the agent's session ends (installed by
   `wizard setup`).
2. The hook calls `wizard capture --close --transcript <path> --agent <id> --agent-session-id <uuid>`.
3. `wizard capture` finds the wizard session matching `--session-id` (written
   by `session_start`) or the most recent unsynthesised session within 24h,
   sets `transcript_path`, `agent`, and `agent_session_id`, then calls
   `Synthesiser` which routes to `OllamaAdapter` (native `/api/chat`, no
   grammar constraint, `think:false`) for Ollama backends, or to LiteLLM for
   cloud providers, and saves the resulting notes to SQLite.
   On success, `WizardSession.is_synthesised` is set to `True`.
   Raw transcript JSONL is persisted to `wizardsession.transcript_raw` before
   synthesis so re-synthesis remains possible after the agent deletes the file.

**Synthesis is fully decoupled from the MCP server.** It runs at hook time,
before the next session starts. No `ctx.sample()` involved — no round-trip
cost, no dependency on MCP context availability.

**Fallback:** If the LLM server is unreachable, `wizard capture` exits non-zero.
The session retains its `transcript_path` (`is_synthesised` stays `False`). Retry
with `wizard capture --close --session-id <id>` when the server is available.

**Key files:**

- `transcript.py` — `TranscriptReader` (JSONL parser)
- `synthesis.py` — `Synthesiser` (backend selection + note persistence)
- `llm_adapters.py` — `OllamaAdapter`, `complete()` (LiteLLM call), `probe_backend_health()`, JSON parsing
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

**Task matching:** `Synthesiser` always sets `task_id=None` on notes.
Wizard owns task matching — the LLM is not shown the task list.

**Limitations:**

- No mid-session intelligence — synthesis runs at session boundaries only
- Transcript file must exist at synthesis time; if deleted, falls back to `wizardsession.transcript_raw` (persisted at capture time)
- Parsers: Claude Code (full), Codex, Gemini, OpenCode, Copilot CLI
- Ollama backends require a running Ollama server; cloud backends require a valid API key
