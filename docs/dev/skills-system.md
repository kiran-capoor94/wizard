# Skills System — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Skills System

Skills are Markdown-based instruction sets that shape how the agent behaves during
specific workflows (session start, task work, code review, etc.). The system has two
storage locations, two file types, and a dedup mechanism for `task_start`.

---

## Two directories

| Directory                       | Purpose                                        | Priority |
| ------------------------------- | ---------------------------------------------- | -------- |
| `~/.wizard/skills/`             | Installed skills (copied by `wizard setup`)    | Higher   |
| `src/wizard/skills/` (package)  | Bundled default skills shipped with the package | Fallback |

`load_skill()` and `load_skill_post()` always check the installed directory first.
If a skill is found there, the package version is ignored. This lets users customise
skills in `~/.wizard/skills/` without editing the package.

Canonical skill names are defined as module-level constants in `src/wizard/skills.py`
(e.g. `SKILL_SESSION_START = "session-start"`). Use these constants in code — never
magic strings.

---

## `SKILL.md` vs `SKILL-POST.md`

Each skill directory may contain two files:

| File           | Copied to agent dirs? | Used as                       | Read by                     |
| -------------- | --------------------- | ----------------------------- | --------------------------- |
| `SKILL.md`     | Yes                   | Agent-facing instructions     | Agent, `get_modes`, etc.    |
| `SKILL-POST.md`| No                    | Tool response `skill_instructions` | Injected by tools only  |

`SKILL.md` is copied to the agent's skills directory (e.g. `~/.claude/skills/`) by
`wizard setup`. The agent reads it as part of its context. It is also parsed by
`build_available_modes()` for frontmatter metadata.

`SKILL-POST.md` is never registered or copied anywhere. It is read by `load_skill_post()`
and injected into specific tool responses as the `skill_instructions` field. This allows
post-call hard gates, schema references, and presentation rules to travel with the response
without bloating the agent's always-on context.

---

## `load_skill()` and `load_skill_post()` resolution

Both functions iterate `(settings.paths.installed_skills, settings.paths.package_skills)`
and return the first file found:

```python
for root in (settings.paths.installed_skills, settings.paths.package_skills):
    path = root / name / "SKILL.md"   # or "SKILL-POST.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
```

Returns `None` if not found in either location. OSError on read logs a warning and
returns `None` (no crash).

---

## `SkillsDirectoryProvider` in `mcp_instance.py`

```python
_roots = [p for p in [settings.paths.installed_skills, settings.paths.package_skills] if p.exists()]
if _roots:
    mcp.add_provider(SkillsDirectoryProvider(roots=_roots))
```

`SkillsDirectoryProvider` (from FastMCP) exposes skills as MCP resources so agents can
list and read them via the MCP protocol. Both roots are passed; FastMCP merges them.
Only existing paths are included — missing directories are silently skipped.

---

## How modes work: `build_available_modes()`

`build_available_modes()` lives in `src/wizard/tools/mode_tools.py`. It reads `SKILL.md`
frontmatter from each skill directory under both roots and filters to skills listed in
`settings.modes.allowed`. The YAML frontmatter `name` and `description` fields are surfaced
to the agent via `SessionStartResponse.available_modes`.

Example frontmatter in `SKILL.md`:

```yaml
---
name: session-start
description: Use when beginning a coding session...
---
```

---

## `skill_instructions` dedup in `task_start`

`task_start` injects `SKILL-POST.md` content as `skill_instructions` in its response —
but only on the first call per FastMCP session. The dedup is keyed by
`ctx.state["task_start_skill_delivered"]`:

```python
skill_delivered = await ctx.get_state("task_start_skill_delivered")
if not skill_delivered:
    skill = load_skill_post(SKILL_TASK_START)
    await ctx.set_state("task_start_skill_delivered", True)
    ...
    skill_instructions=skill
```

Subsequent `task_start` calls within the same session return `skill_instructions=None`.
This prevents the post-call instructions from being injected redundantly when the engineer
works on multiple tasks in a single session.

---

## How to add a new skill

1. Create `src/wizard/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`).
2. Optionally create `src/wizard/skills/<name>/SKILL-POST.md` for post-call injection.
3. Add a module-level constant in `src/wizard/skills.py`:
   ```python
   SKILL_MY_SKILL = "my-skill"
   ```
4. Call `load_skill_post(SKILL_MY_SKILL)` in the relevant tool response if needed.
5. Run `wizard setup` (or `wizard update`) to copy `SKILL.md` to the agent's skills directory.
