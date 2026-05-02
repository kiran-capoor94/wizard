# services — AI Fact Sheet

Source: `src/wizard/services.py`

---

## `SessionCloser`

**Purpose:** Auto-closes abandoned sessions (no summary, `closed_by` is `NULL` or `"hook"`) using synthetic summaries. No LLM calls — summary text is deterministically generated.

**Constructor:**

| Arg | Type | Default | Description |
|---|---|---|---|
| `note_repo` | `NoteRepository \| None` | `NoteRepository()` | Injected for note persistence |
| `security` | `SecurityService \| None` | `SecurityService()` | PII scrubbing before summary write |
| `settings` | `Settings \| None` | `None` | Unused in current close path; available for future use |

**Public methods:**

| Method | Args | Returns | Description |
|---|---|---|---|
| `close_recent_abandoned` | `db, current_session_id: int` | `list[ClosedSessionSummary]` | Inline path: closes sessions abandoned within the last **2h**; runs inside `session_start` |
| `close_abandoned_background` | `current_session_id: int` | `None` (coroutine) | Background path: closes sessions older than **2h** with no summary; opens its own DB session |

**Abandonment criteria (both paths):**
- `summary IS NULL`
- `closed_by IS NULL OR closed_by == "hook"`
- `id != current_session_id`

**Threshold differences:**

| Path | Age filter | Limit | Transport safety |
|---|---|---|---|
| `close_recent_abandoned` | `created_at >= now - 2h` | 3 sessions | Inline; **must not call `ctx.sample()`** — deadlocks stdio transport |
| `close_abandoned_background` | `created_at < now - 2h` | none | Async task; independent DB session; errors captured by Sentry |

**`_close_one` sequence (shared by both paths):**
1. Cancel any in-flight mid-session synthesis (`cancel_mid_session_synthesis(session.agent_session_id)`).
2. Load all notes for the session ordered by `created_at ASC`.
3. Deduplicate `task_ids` from notes.
4. Build `SessionState` with `closure_status="interrupted"`, empty intent/delta/loops.
5. Generate synthetic summary: `"Auto-closed: N note(s) across M task(s). Last activity: <timestamp>."` — `closed_via="synthetic"`.
6. Scrub summary through `SecurityService.scrub()`.
7. Set `session.summary`, `session.session_state`; if `closed_by is None` → set to `"auto"`.
8. Flush session row.
9. Write a `NoteType.SESSION_SUMMARY` note via `NoteRepository.save()`.
10. Return `ClosedSessionSummary`.

**Invariants:**
- **`closed_by = "auto"` only if `closed_by` was previously `NULL`; `"hook"`-closed sessions keep their original `closed_by`.**
- **No LLM calls in any close path** — synthetic summary is template-based.
- PII scrubbed before write, not on read.

---

## `RegistrationService`

**Purpose:** Manages agent registration, skill install/uninstall, config init, and `~/.wizard` lifecycle.

**Constructor:**

| Arg | Type | Description |
|---|---|---|
| `settings` | `Settings` | Config object; `settings.db` parent dir becomes `WIZARD_HOME` |

`self.WIZARD_HOME = Path(settings.db).parent`

**Public methods:**

| Method | Args | Returns | Description |
|---|---|---|---|
| `ensure_wizard_home` | — | `None` | `mkdir -p WIZARD_HOME` |
| `initialize_config` | — | `str` | Creates `config.json` with defaults if absent; adds `modes.allowed` from `WIZARD_MODES` |
| `initialize_allowlist` | — | `str` | Creates empty `allowlist.txt` if absent |
| `refresh_skills` | `source_override: Path \| None` | `str` | Removes and re-copies `skills/` from package to `WIZARD_HOME/skills/`; merges `WIZARD_MODES` into `config.json` |
| `register_agents` | `agent_ids: list[str]` | `list[dict]` | Registers MCP, hook, and skills for each agent; returns per-agent result dicts |
| `deregister_agents` | `agent_ids: list[str]` | `list[dict]` | Deregisters MCP, hook, and skills for each agent; returns per-agent result dicts |
| `uninstall_wizard` | — | `str` | `shutil.rmtree(WIZARD_HOME)` |
| `ensure_editable_pth` | — (staticmethod) | `None` | Clears `UF_HIDDEN` macOS flag from hatchling editable `.pth` file |

**`register_agents` step-by-step (per agent):**
1. `agent_registration.register(aid)` — writes MCP server entry to agent config; appends `"MCP"` to `parts`.
2. `agent_registration.register_hook(aid)` — if successful, appends `"hook"` to `parts`.
3. `agent_registration.install_skills(aid, source)` — if skills dir exists and install succeeds, appends `"skills"` to `parts`.
4. Sets `res["success"] = True`. Any exception sets `res["error"]` and leaves `success = False`.

**`deregister_agents` step-by-step (per agent):**
1. `agent_registration.deregister(aid)` — removes MCP entry; appends `"MCP"`.
2. `agent_registration.deregister_hook(aid)` — if successful, appends `"hook"`.
3. `agent_registration.uninstall_skills(aid, source)` — if skills dir exists and uninstall succeeds, appends `"skills"`.

**`refresh_hooks` — module-level function in `agent_registration`, not a method of `RegistrationService`:**
- Copies hook scripts from installed package (`wizard/hooks/`) to `~/.wizard/hooks/`.
- Removes any files in destination not present in the package (full sync).
- Called by: `wizard setup` and `wizard update`.

**CLI commands that use these methods:**

| CLI command | Methods called |
|---|---|
| `wizard setup` | `ensure_wizard_home`, `initialize_config`, `initialize_allowlist`, `ensure_editable_pth`, `refresh_skills`, `register_agents` |
| `wizard uninstall` | `deregister_agents`, `uninstall_wizard` |
| `wizard update` | `deregister_agents` (old), `refresh_skills`, `register_agents` (new) |

**`refresh_hooks` (`agent_registration` module function) is called by:**
- `wizard setup` (after `ensure_editable_pth`, before `refresh_skills`)
- `wizard update` (after migration, before `register_agents`)

**Result dict shape:**
```python
{"id": str, "success": bool, "parts": list[str], "error": str | None}
```
`parts` elements: `"MCP"`, `"hook"`, `"skills"` — present only if that step succeeded.

**Invariants:**
- **`deregister_agents` is called on the OLD registered agents before `register_agents` during `wizard update`** — ensures stale skills/hooks from previous version are removed before new ones are installed.
- `initialize_config` is idempotent — does nothing if `config.json` already exists.
- `refresh_skills` is destructive — removes entire `skills/` dir then re-copies; safe because source is the installed package.
