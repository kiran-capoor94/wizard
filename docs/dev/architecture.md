# Project Layout — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Project Layout

```text
server.py                    # Entry point — imports mcp_instance, tools, resources, prompts
apm.yml                      # Single-command agent setup (all agents, hooks, skills)
src/wizard/
  cli/
    main.py                  # Typer app: setup, configure, doctor, analytics, dashboard, update, uninstall
    serve.py                 # wizard-server entry point (installed MCP binary)
    capture.py               # wizard capture — transcript synthesis trigger (called by hooks)
    configure.py             # configure knowledge-store + synthesis backends subcommands
    doctor.py                # 8-point health checks (wizard doctor); allowlist check is advisory (non-failing)
    analytics.py             # Session/note/task usage stats (wizard analytics)
    dashboard.py             # Streamlit health dashboard — 5 panels: active session, recent notes, synthesis health, memory utilisation, tool call frequency
    verify.py                # `wizard verify` — 5-step MCP handshake smoke test
  mcp_instance.py            # FastMCP app factory; registers ToolLoggingMiddleware + skills
  skills.py                  # Skill loader (reads ~/.wizard/skills/ at startup)
  synthesis_prompt.py        # Transcript filtering and prompt construction for synthesis (`filter_for_synthesis`, `format_prompt`, `KEEP_RESULT_TOOLS`, `ROLE_CHAR_LIMITS`)
  tools/                       # MCP tools package (split by domain)
    __init__.py                # Re-exports all tool functions
    session_tools.py           # session_start, session_end, resume_session
    session_helpers.py         # build_prior_summaries, find_previous_session_id, mid-session synthesis loop
    task_tools.py              # task_start, save_note, update_task, create_task
    note_tools.py              # rewind_task, what_am_i_missing
    task_fields.py             # apply_task_fields + elicitation helpers (mental model, done confirm, duplicate check)
    formatting.py              # task_contexts_to_json — session response serialisation
    mode_tools.py              # get_modes, set_mode — working mode activation
    triage_tools.py            # what_should_i_work_on (mode-based scoring + LLM reasons)
    meeting_tools.py           # get_meeting, save_meeting_summary, ingest_meeting
    query_tools.py             # get_tasks, get_task, get_sessions, get_session, search (paginated, no session required)
  repositories/              # Query layer (package)
    task.py                  # TaskRepository
    note.py                  # NoteRepository
    meeting.py               # MeetingRepository
    session.py               # SessionRepository
    task_state.py            # TaskStateRepository
    search.py                # SearchRepository — FTS5 fan-out across notes/sessions/meetings/tasks; BM25 ranked
    analytics.py             # AnalyticsRepository — tool call frequency, session/note/task usage stats
  resources.py               # 5 read-only MCP resources (wizard://* URIs)
  prompts.py                 # MCP prompt templates
  middleware.py              # ToolLoggingMiddleware (Sentry spans per tool) + SessionStateMiddleware (session snapshot + Sentry user tag)
  transcript.py              # TranscriptReader (JSONL parser for agent transcripts)
  synthesis.py               # Synthesiser (auto-capture — ordered backend failover)
  llm_adapters.py            # OllamaAdapter + LiteLLM completion wrapper, probe_backend_health, JSON parsing
  mid_session.py             # Background mid-session synthesis state (MID_SESSION_TASKS dict)
  models.py                  # SQLModel ORM: task, note, meeting, wizardsession, toolcall, task_state
  schemas.py                 # Pydantic response types for all MCP tools (incl. SearchResult, SearchResponse)
  services.py                # `SessionCloser` (auto-closes abandoned sessions) + `RegistrationService` (agent registration, setup, uninstall)
  security.py                # SecurityService + HeuristicNameFinder + PseudonymStore — PII scrubbing with pseudonymisation
  config.py                  # Pydantic Settings + BackendConfig + ModesSettings + JsonConfigSettingsSource
  database.py                # SQLite session factory (SQLModel engine)
  deps.py                    # FastMCP Depends() provider functions (incl. get_skill_roots, get_search_repo)
  exceptions.py              # ConfigurationError
  agent_registration.py      # Write MCP + hook config into agent JSON/TOML files; refresh_hooks()
  alembic/                   # DB migrations — bundled in package for `wizard update`
  hooks/                     # Hook scripts — bundled in package, copied to ~/.wizard/hooks/ on setup
  skills/                    # FastMCP skills source (copied to ~/.wizard/skills/ by setup)
    architect/               # Architect mode skill
      SKILL.md
      references/            # Sub-skills loaded as supporting context when architect mode is active
        arch-review.md       # Architecture audit protocol
        constraints-designer.md  # Constraints/invariants elicitation protocol
    ideation/                # Ideation mode skill (SKILL.md)
    product-owner/           # Product-owner mode skill (SKILL.md)
    caveman/                 # Compressed output skill (SKILL.md) — low-token output mode
    rulecheck/               # Guideline violation scanner + fix PR orchestrator (SKILL.md)
    wizard-playground/       # Mermaid diagram workbench (invocable skill, not a mode)
hooks/                       # Hook scripts source (also bundled as src/wizard/hooks/ for installs)
  session-end.sh             # Claude Code SessionEnd hook — calls `wizard capture --close` to synthesise transcript
  session-start.sh           # Claude Code SessionStart hook — personalization refresh (80%) + session boot injection
  session-start-minimal.sh   # Minimal session-start for Gemini/Codex/Copilot — boot injection only, no 80% gate
alembic/                     # DB migration scripts (dev use; bundled copy lives in src/wizard/alembic/)
tests/
  scenarios/                 # ALL tests live here — scenario/behaviour tests only (no unit tests)
  conftest.py                # shared fixtures
  fakes.py                   # in-memory fakes for repositories
```
