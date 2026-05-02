# Synthesis

Synthesis is wizard's automatic note-taking feature. At the end of a session — and every 5 minutes while a session is active — wizard reads your conversation transcript and extracts structured notes from it. You don't need to remember to save notes manually; synthesis does it for you.

## Prerequisites

Synthesis requires a running LLM. The easiest setup is a local [Ollama](https://ollama.com/) instance with a model pulled and ready. You can also use a cloud model like GPT-4o, but a local model is faster and works offline.

## How to enable synthesis

Synthesis is enabled by default, but it needs a model configured before it will do anything. Add this to `~/.wizard/config.json`:

```json
{
  "synthesis": {
    "enabled": true,
    "model": "ollama/gemma4:latest-64k",
    "base_url": "http://localhost:11434"
  }
}
```

If you haven't set up Ollama yet, `ollama serve` starts the server, and `ollama pull gemma4:latest-64k` downloads the model.

Use `wizard configure synthesis add` to manage backends interactively instead of editing JSON by hand. See [configuration.md](configuration.md) for the full set of synthesis options.

## What gets extracted

Wizard instructs the LLM to extract six types of notes from your conversation:

| Type | What it captures |
|---|---|
| `investigation` | Findings and exploration — what you discovered, what you tried, what you learned about how something works |
| `decision` | Resolved choices — what you decided and why, enough context to understand the reasoning later |
| `docs` | How things work — factual descriptions of systems, APIs, or processes that came up during the session |
| `learnings` | Surprises and corrections — things that weren't obvious, common misconceptions corrected, unexpected behaviour |
| `session_summary` | A structured end-of-session summary — written by `session_end`, not by synthesis |
| `failure` | What didn't work — failed approaches, dead ends, and why they were abandoned |

Synthesis doesn't extract a note for every message. It looks for content that's actually worth keeping — a finding, a decision, something surprising — and skips filler.

## Task matching

When synthesis extracts a note, it also tries to associate it with one of your open tasks. The LLM receives a table of your current open tasks and their IDs, and assigns a `task_id` to each note. Wizard then validates that the task ID exists — if the LLM guesses wrong, the note is anchored to the session instead.

This means your notes show up in the right task context the next time you call `wizard:task_start`, without you having to manually link anything.

## How to retry failed synthesis

If a session's synthesis failed (the LLM was unavailable, timed out, or returned bad output), wizard marks the session with `synthesis_status = "partial_failure"`. You can retry it once the LLM is available:

```bash
wizard capture --close --session-id <id>
```

Replace `<id>` with the session ID from `wizard analytics` or from the failure message.

## Synthesis status

Each session has a `synthesis_status` field:

| Status | Meaning |
|---|---|
| `pending` | Session exists; synthesis hasn't run yet |
| `complete` | Synthesis ran successfully and all notes were saved |
| `partial_failure` | Synthesis ran but at least one chunk failed; some notes may be missing |

Check the status for recent sessions with `wizard analytics`. A pattern of `partial_failure` usually means the LLM backend is unavailable or overloaded.

## Common issue: synthesis produces no notes

If synthesis runs but doesn't produce any notes, check the following:

1. **Is synthesis enabled?** Confirm `synthesis.enabled: true` in `~/.wizard/config.json`.
2. **Is the LLM running?** For Ollama: `curl http://localhost:11434` should return a response. If it doesn't, run `ollama serve`.
3. **Is the model correct?** The model string must include the provider prefix, e.g. `ollama/gemma4:latest-64k` not just `gemma4:latest-64k`.
4. **Check recent session status:** `wizard analytics` shows `synthesis_status` for recent sessions. If they're all `pending`, synthesis isn't running at all — check that `synthesis.enabled` is set.

If the session shows `partial_failure`, the backend was reachable but the synthesis call failed. Retry with `wizard capture --close --session-id <id>`.
