# Skills Reference

Sources: `src/wizard/skills.py`, `src/wizard/mcp_instance.py`, `src/wizard/tools/mode_tools.py`

---

## Skill constants

Defined in `src/wizard/skills.py`:

| Constant | Value (skill name) |
|----------|-------------------|
| `SKILL_SESSION_START` | `"session-start"` |
| `SKILL_SESSION_RESUME` | `"session-resume"` |
| `SKILL_SESSION_END` | `"session-end"` |
| `SKILL_TASK_START` | `"task-start"` |
| `SKILL_MEETING` | `"meeting"` |
| `SKILL_ARCHITECTURE_DEBATE` | `"architecture-debate"` |
| `SKILL_CODE_REVIEW` | `"code-review"` |
| `SKILL_NOTE` | `"note"` |
| `SKILL_TRIAGE` | `"what-should-i-work-on"` |

---

## `load_skill(name)`

Reads `SKILL.md` for the named skill.

**Resolution order:**
1. `settings.paths.installed_skills / name / SKILL.md` (`~/.wizard/skills/<name>/SKILL.md`)
2. `settings.paths.package_skills / name / SKILL.md` (`src/wizard/skills/<name>/SKILL.md`)

Returns `str` content on success. Returns `None` if not found in either location (logs debug). Returns `None` and logs warning on `OSError`.

---

## `load_skill_post(name)`

Reads `SKILL-POST.md` for the named skill.

**Resolution order:** same as `load_skill` — installed first, then package.

Returns `str` or `None`.

**`SKILL-POST.md` is never copied to agent skill directories** (`install_skills()` excludes it via `shutil.ignore_patterns("SKILL-POST.md")`).

**Purpose:** post-call schema reference, hard gates, and presentation rules. Injected into tool responses as the `skill_instructions` field. Tools that use it:
- `task_start` → `SKILL_TASK_START`
- `session_end` → `SKILL_SESSION_END`
- `resume_session` → `SKILL_SESSION_RESUME`
- `ingest_meeting` / `get_meeting` → `SKILL_MEETING`

---

## `SkillsDirectoryProvider` in `mcp_instance.py`

`src/wizard/mcp_instance.py` adds a FastMCP `SkillsDirectoryProvider` that serves skills as MCP resources:

```python
_roots = [p for p in [settings.paths.installed_skills, settings.paths.package_skills] if p.exists()]
if _roots:
    mcp.add_provider(SkillsDirectoryProvider(roots=_roots))
```

Roots are only included if they exist at startup time.

---

## Skills directories

| Path | Description | Checked order |
|------|-------------|---------------|
| `~/.wizard/skills/` | `settings.paths.installed_skills` — user-editable, takes priority | First |
| `src/wizard/skills/` | `settings.paths.package_skills` — read-only package source | Second |

Both paths are defined on `settings.paths`. `~/.wizard/skills/` is populated by `wizard setup` / `wizard update` from the package source.

---

## `build_available_modes(modes, roots=None)`

Defined in `src/wizard/tools/mode_tools.py`.

**Reads:** `modes.allowed` list from `settings.modes` (configured in `~/.wizard/config.json`)

**For each skill name in `modes.allowed`:**
1. Looks up `<root>/<name>/SKILL.md` in each root (installed first, then package)
2. Parses YAML frontmatter (`---` block) with `yaml.safe_load`
3. Extracts `description` field from frontmatter
4. Returns `ModeInfo(name=name, description=description)`

**Returns:** `list[ModeInfo]` — only includes skills whose `SKILL.md` was found and parsed. Skills not found in any root are silently skipped.

Called by: `get_modes` tool and `session_start` tool (to populate `available_modes` in the session-start response).

---

## `task_start` skill dedup

`skill_instructions` (from `load_skill_post(SKILL_TASK_START)`) is sent **only on the first `task_start` call per session**.

**Mechanism:** FastMCP session state key `"task_start_skill_delivered"`.

```python
skill_delivered = await ctx.get_state("task_start_skill_delivered")
skill = None if skill_delivered else load_skill_post(SKILL_TASK_START)
if not skill_delivered:
    await ctx.set_state("task_start_skill_delivered", True)
```

On first call: `skill_delivered` is `None` → `skill` is loaded → state set to `True`.
On subsequent calls: `skill_delivered` is `True` → `skill` is `None` → `skill_instructions` field is `None`.

---

## How to add a new skill

1. Create `src/wizard/skills/<name>/SKILL.md` — YAML frontmatter with `description:` field, followed by skill content.
2. Optionally create `src/wizard/skills/<name>/SKILL-POST.md` — post-call instructions (schema, gates, presentation rules). **Never deployed to agent dirs.**
3. Add a `SKILL_<NAME>` constant in `src/wizard/skills.py`.
4. To make it a selectable mode: add the name to `modes.allowed` in `~/.wizard/config.json` (or `WIZARD_MODES` in `src/wizard/config.py`).
5. Run `wizard update` or `wizard setup` to deploy to agent skill directories.
