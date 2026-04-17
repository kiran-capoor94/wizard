# Setup Interactive Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `wizard setup` collect all integration credentials interactively, run Notion schema discovery inline, and give verbose feedback at every step — so the user ends setup with a fully populated config.

**Architecture:** All changes are in `src/wizard/cli/main.py`. Two new private helpers (`_configure_notion`, `_configure_jira`) encapsulate credential collection and are called from `setup()`. The existing `_run_notion_discovery` is called from `_configure_notion`. A `--jira` flag is added to `configure()`.

**Tech Stack:** Python, Typer, notion-client v3, uv pytest

---

## File Map

| File | Change |
|------|--------|
| `src/wizard/cli/main.py` | Add `_notion_is_configured`, `_jira_is_configured`, `_configure_notion`, `_configure_jira` helpers; rewrite `setup()` integration selection; add `--jira` to `configure()`; improve `_run_notion_discovery` output |
| `tests/test_cli.py` | Update existing setup tests (new prompt sequence); add new tests for each new behaviour |

---

### Task 1: Add integration selection to `setup()` + update existing tests

The current setup has one prompt (daily_page_parent_id). The new setup asks for integrations first. All existing tests that invoke setup must supply input for this new prompt.

**Files:**
- Modify: `src/wizard/cli/main.py` (setup function, lines 167–247)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for integration selection**

Add to `tests/test_cli.py`:

```python
def test_setup_asks_which_integrations(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="4\n")
    assert result.exit_code == 0
    assert "integration" in result.output.lower()


def test_setup_integration_invalid_selection_exits(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="9\n")
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::test_setup_asks_which_integrations tests/test_cli.py::test_setup_integration_invalid_selection_exits -v
```

Expected: FAIL (no integration selection prompt exists yet)

- [ ] **Step 3: Replace the daily_page_parent_id block in `setup()` with integration selection**

In `src/wizard/cli/main.py`, replace lines 188–199 (the `daily_page_parent_id` block) with:

```python
    typer.echo("\nWhich integrations would you like to configure?")
    typer.echo("  1. Notion")
    typer.echo("  2. Jira")
    typer.echo("  3. Both")
    typer.echo("  4. Neither")
    int_selection = typer.prompt("Enter number (1-4)")
    try:
        int_idx = int(int_selection)
        if int_idx not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        typer.echo("Invalid selection.", err=True)
        raise typer.Exit(1)

    configure_notion = int_idx in (1, 3)
    configure_jira = int_idx in (2, 3)
```

- [ ] **Step 4: Update all existing setup tests that use `input="\n"` to use `input="4\n"` (select neither)**

In `tests/test_cli.py`, update the `input` argument in these tests:
- `test_setup_creates_wizard_dir`: `input="\n"` → `input="4\n"`
- `test_setup_creates_default_config`: `input="\n"` → `input="4\n"`
- `test_setup_copies_skills`: `input="\n"` → `input="4\n"`
- `test_setup_handles_missing_skills_source`: `input="\n"` → `input="4\n"`
- `test_setup_is_idempotent`: both `invoke` calls → `input="4\n"`
- `test_setup_registers_mcp_in_claude_configs`: `input="\n"` → `input="4\n"`
- `test_setup_skips_mcp_when_config_missing`: `input="\n"` → `input="4\n"`
- `test_setup_agent_flag_registers_gemini`: `input="\n"` → `input="4\n"`
- `test_setup_agent_all_registers_all_five`: `input="\n"` → `input="4\n"`
- `test_setup_writes_registered_agents_json`: `input="\n"` → `input="4\n"`
- `test_setup_runs_migrations_when_db_missing`: `input="\n"` → `input="4\n"`
- `test_setup_skips_migrations_when_db_healthy`: `input="\n"` → `input="4\n"`
- `test_setup_exits_nonzero_when_migrations_fail`: `input="\n"` → `input="4\n"`
- `test_setup_interactive_prompt_selects_agent`: `input="\n3\n"` → `input="4\n3\n"` (select neither, then gemini)
- `test_setup_interactive_prompt_invalid_selection`: `input="\n99\n"` → `input="4\n99\n"`

Also delete `test_setup_saves_daily_page_parent_id_when_provided` and `test_setup_skips_daily_page_prompt_when_already_set` — these will be replaced by Notion-flow tests in Task 2.

- [ ] **Step 5: Run all setup tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py -k "setup" -v
```

Expected: All PASS (including the two new integration-selection tests)

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: add integration selection prompt to wizard setup"
```

---

### Task 2: Add `_configure_notion` helper

Collects Notion credentials, saves them, and runs schema discovery.

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_setup_notion_collects_token_and_ids(tmp_path):
    """Selecting Notion (1) prompts for token, daily page ID, tasks ID, meetings ID."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\nmy-page-id\nmy-tasks-id\nmy-meetings-id\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["token"] == "my-token"
    assert cfg["notion"]["daily_page_parent_id"] == "my-page-id"
    assert cfg["notion"]["tasks_ds_id"] == "my-tasks-id"
    assert cfg["notion"]["meetings_ds_id"] == "my-meetings-id"


def test_setup_notion_runs_discovery(tmp_path):
    """After collecting Notion credentials, setup calls _run_notion_discovery."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery") as mock_disc:
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nmy-tasks-id\nmy-meetings-id\n",
            )
    mock_disc.assert_called_once()


def test_setup_notion_optional_daily_page_id_can_be_skipped(tmp_path):
    """Pressing Enter on daily page ID prompt skips it (leaves field empty)."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"):
            mock_ar.read_registered_agents.return_value = []
            runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\nmy-tasks-id\nmy-meetings-id\n",
            )
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["daily_page_parent_id"] == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::test_setup_notion_collects_token_and_ids tests/test_cli.py::test_setup_notion_runs_discovery tests/test_cli.py::test_setup_notion_optional_daily_page_id_can_be_skipped -v
```

Expected: FAIL

- [ ] **Step 3: Add `_configure_notion` helper and wire into `setup()`**

Add this function to `src/wizard/cli/main.py` before the `setup` command:

```python
def _configure_notion(cfg: dict, config_path: Path) -> None:
    """Prompt for all Notion credentials, save to config, run schema discovery."""
    typer.echo("\nNotion integration")
    token = typer.prompt("  Notion integration token (notion.so/profile/integrations)")
    cfg.setdefault("notion", {})["token"] = token
    typer.echo("  token: set")

    page_id = typer.prompt("  Daily page parent ID (Enter to skip)", default="")
    cfg["notion"]["daily_page_parent_id"] = page_id
    typer.echo(f"  daily page ID: {'set' if page_id else 'skipped'}")

    tasks_id = typer.prompt("  Tasks database ID")
    cfg["notion"]["tasks_ds_id"] = tasks_id
    typer.echo("  tasks database: set")

    meetings_id = typer.prompt("  Meetings database ID")
    cfg["notion"]["meetings_ds_id"] = meetings_id
    typer.echo("  meetings database: set")

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    _run_notion_discovery(config_path)
```

Then in `setup()`, after the integration selection block, add:

```python
    if configure_notion:
        _configure_notion(cfg, config_path)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_setup_notion_collects_token_and_ids tests/test_cli.py::test_setup_notion_runs_discovery tests/test_cli.py::test_setup_notion_optional_daily_page_id_can_be_skipped -v
```

Expected: PASS

- [ ] **Step 5: Run full suite to confirm nothing broke**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: add _configure_notion helper — collects credentials and runs discovery"
```

---

### Task 3: Add `_configure_jira` helper

Collects Jira credentials and saves them to config.

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_setup_jira_collects_all_fields(tmp_path):
    """Selecting Jira (2) prompts for base_url, project_key, email, token."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="2\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-api-token\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["jira"]["base_url"] == "https://acme.atlassian.net"
    assert cfg["jira"]["project_key"] == "ENG"
    assert cfg["jira"]["email"] == "dev@acme.com"
    assert cfg["jira"]["token"] == "jira-api-token"


def test_setup_both_configures_notion_and_jira(tmp_path):
    """Selecting Both (3) runs both _configure_notion and _configure_jira."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="3\nmy-token\n\ntasks-id\nmeetings-id\nhttps://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
            )
    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["notion"]["token"] == "my-token"
    assert cfg["jira"]["token"] == "jira-token"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::test_setup_jira_collects_all_fields tests/test_cli.py::test_setup_both_configures_notion_and_jira -v
```

Expected: FAIL

- [ ] **Step 3: Add `_configure_jira` helper and wire into `setup()`**

Add to `src/wizard/cli/main.py` before the `setup` command:

```python
def _configure_jira(cfg: dict, config_path: Path) -> None:
    """Prompt for all Jira credentials and save to config."""
    typer.echo("\nJira integration")
    base_url = typer.prompt("  Base URL (e.g. https://yourorg.atlassian.net)")
    cfg.setdefault("jira", {})["base_url"] = base_url
    typer.echo(f"  base_url: {base_url}")

    project_key = typer.prompt("  Project key (e.g. ENG)")
    cfg["jira"]["project_key"] = project_key
    typer.echo(f"  project_key: {project_key}")

    email = typer.prompt("  Email")
    cfg["jira"]["email"] = email
    typer.echo("  email: set")

    token = typer.prompt("  API token (id.atlassian.com/manage-profile/security/api-tokens)")
    cfg["jira"]["token"] = token
    typer.echo("  token: set")

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
```

Then in `setup()`, after the `configure_notion` block, add:

```python
    if configure_jira:
        _configure_jira(cfg, config_path)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_setup_jira_collects_all_fields tests/test_cli.py::test_setup_both_configures_notion_and_jira -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: add _configure_jira helper — collects Jira credentials"
```

---

### Task 4: Skip already-configured integrations + print final summary

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_setup_skips_notion_when_already_configured(tmp_path):
    """If Notion token + DB IDs are already set, skip prompts and print hint."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    cfg = {
        "notion": {
            "token": "existing-token",
            "tasks_ds_id": "existing-tasks",
            "meetings_ds_id": "existing-meetings",
            "daily_page_parent_id": "",
        },
        "jira": {"base_url": "", "project_key": "", "token": "", "email": ""},
        "scrubbing": {"enabled": True, "allowlist": []},
    }
    (wizard_dir / "config.json").write_text(json.dumps(cfg))

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery") as mock_disc:
            mock_ar.read_registered_agents.return_value = []
            # Select Notion (1) — but it should be skipped
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="1\n")

    assert result.exit_code == 0
    mock_disc.assert_not_called()
    assert "already configured" in result.output.lower()
    assert "wizard configure --notion" in result.output


def test_setup_skips_jira_when_already_configured(tmp_path):
    """If all Jira fields are set, skip prompts and print hint."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    cfg = {
        "notion": {"token": "", "tasks_ds_id": "", "meetings_ds_id": "", "daily_page_parent_id": ""},
        "jira": {
            "base_url": "https://acme.atlassian.net",
            "project_key": "ENG",
            "token": "existing-token",
            "email": "dev@acme.com",
        },
        "scrubbing": {"enabled": True, "allowlist": []},
    }
    (wizard_dir / "config.json").write_text(json.dumps(cfg))

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar:
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(ctx.app, ["setup", "--agent", "claude-code"], input="2\n")

    assert result.exit_code == 0
    assert "already configured" in result.output.lower()
    assert "wizard configure --jira" in result.output


def test_setup_final_summary_shows_configured_integrations(tmp_path):
    """Final summary lists Notion as configured and Jira as skipped."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.agent_registration") as mock_ar, \
             patch("wizard.cli.main._run_notion_discovery"):
            mock_ar.read_registered_agents.return_value = []
            result = runner.invoke(
                ctx.app, ["setup", "--agent", "claude-code"],
                input="1\nmy-token\n\ntasks-id\nmeetings-id\n",
            )
    assert result.exit_code == 0
    assert "notion" in result.output.lower()
    assert "configured" in result.output.lower()
    assert "jira" in result.output.lower()
    assert "wizard configure --jira" in result.output
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::test_setup_skips_notion_when_already_configured tests/test_cli.py::test_setup_skips_jira_when_already_configured tests/test_cli.py::test_setup_final_summary_shows_configured_integrations -v
```

Expected: FAIL

- [ ] **Step 3: Add `_notion_is_configured` and `_jira_is_configured` helpers**

Add to `src/wizard/cli/main.py` before `_configure_notion`:

```python
def _notion_is_configured(cfg: dict) -> bool:
    n = cfg.get("notion", {})
    return bool(n.get("token") and n.get("tasks_ds_id") and n.get("meetings_ds_id"))


def _jira_is_configured(cfg: dict) -> bool:
    j = cfg.get("jira", {})
    return bool(j.get("token") and j.get("base_url") and j.get("project_key") and j.get("email"))
```

- [ ] **Step 4: Update the integration block in `setup()` to skip already-configured integrations**

Replace:

```python
    if configure_notion:
        _configure_notion(cfg, config_path)

    if configure_jira:
        _configure_jira(cfg, config_path)
```

With:

```python
    notion_status = "skipped"
    jira_status = "skipped"

    if configure_notion:
        if _notion_is_configured(cfg):
            typer.echo("\nNotion already configured — run 'wizard configure --notion' to update")
            notion_status = "already configured"
        else:
            _configure_notion(cfg, config_path)
            notion_status = "configured"

    if configure_jira:
        if _jira_is_configured(cfg):
            typer.echo("\nJira already configured — run 'wizard configure --jira' to update")
            jira_status = "already configured"
        else:
            _configure_jira(cfg, config_path)
            jira_status = "configured"
```

- [ ] **Step 5: Replace `typer.echo("Setup complete.")` at end of `setup()` with a summary block**

Replace:

```python
    agent_registration.write_registered_agents(agents_to_register)
    typer.echo("Setup complete.")
```

With:

```python
    agent_registration.write_registered_agents(agents_to_register)
    typer.echo("\n" + "─" * 45)
    typer.echo("Setup complete.")
    typer.echo(f"  Notion  {notion_status}" + (
        "" if notion_status not in ("skipped",) else " (run 'wizard configure --notion' to add)"
    ))
    typer.echo(f"  Jira    {jira_status}" + (
        "" if jira_status not in ("skipped",) else " (run 'wizard configure --jira' to add)"
    ))
    agent_label = ", ".join(agents_to_register)
    typer.echo(f"  Agent   {agent_label}")
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_setup_skips_notion_when_already_configured tests/test_cli.py::test_setup_skips_jira_when_already_configured tests/test_cli.py::test_setup_final_summary_shows_configured_integrations -v
```

Expected: PASS

- [ ] **Step 7: Run full suite**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: skip already-configured integrations and print final summary"
```

---

### Task 5: Add `configure --jira` command

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_cli.py`:

```python
def test_configure_jira_prompts_and_saves_fields(tmp_path):
    """configure --jira re-prompts all Jira fields and saves them."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    (wizard_dir / "config.json").write_text(json.dumps({"jira": {}, "notion": {}, "scrubbing": {}}))

    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(
            ctx.app, ["configure", "--jira"],
            input="https://acme.atlassian.net\nENG\ndev@acme.com\njira-token\n",
        )

    assert result.exit_code == 0
    cfg = json.loads((wizard_dir / "config.json").read_text())
    assert cfg["jira"]["base_url"] == "https://acme.atlassian.net"
    assert cfg["jira"]["project_key"] == "ENG"
    assert cfg["jira"]["email"] == "dev@acme.com"
    assert cfg["jira"]["token"] == "jira-token"


def test_configure_no_flags_shows_available_options(tmp_path):
    """configure with no flags prints both --notion and --jira as available."""
    wizard_dir = tmp_path / ".wizard"
    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(ctx.app, ["configure"])
    assert "--notion" in result.output
    assert "--jira" in result.output
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_cli.py::test_configure_jira_prompts_and_saves_fields tests/test_cli.py::test_configure_no_flags_shows_available_options -v
```

Expected: FAIL

- [ ] **Step 3: Add `_run_jira_configure` helper and `--jira` flag to `configure()`**

Add helper before `configure`:

```python
def _run_jira_configure(config_path: Path) -> None:
    if not config_path.exists():
        typer.echo("Config not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)
    with open(config_path) as f:
        cfg = json.load(f)
    _configure_jira(cfg, config_path)
```

Update `configure()`:

```python
@app.command()
def configure(
    notion: bool = typer.Option(False, "--notion", help="Re-run Notion schema discovery"),
    jira: bool = typer.Option(False, "--jira", help="Re-configure Jira credentials"),
) -> None:
    """Configure Wizard integrations."""
    if notion:
        _run_notion_discovery(WIZARD_HOME / "config.json")
        return
    if jira:
        _run_jira_configure(WIZARD_HOME / "config.json")
        return
    typer.echo("Available flags: --notion, --jira")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_cli.py::test_configure_jira_prompts_and_saves_fields tests/test_cli.py::test_configure_no_flags_shows_available_options -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: add configure --jira for Jira reconfiguration"
```

---

### Task 6: Improve `_run_notion_discovery` verbose output

Update output to match the design: `→` arrow format for matched fields, "Discovering schema..." header, "Schema saved." footer.

**Files:**
- Modify: `src/wizard/cli/main.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_cli.py`:

```python
def test_configure_notion_prints_arrow_format(tmp_path):
    """_run_notion_discovery prints matched fields as 'field → Property'."""
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    config = {
        "notion": {
            "token": "test-token",
            "tasks_ds_id": "tasks-db",
            "meetings_ds_id": "meetings-db",
        }
    }
    (wizard_dir / "config.json").write_text(json.dumps(config))

    with _fresh_app(wizard_dir) as ctx:
        with patch("wizard.cli.main.notion_discovery") as mock_nd, \
             patch("wizard.cli.main.NotionSdkClient"):
            mock_nd.fetch_db_properties.return_value = {"Task": "title", "Status": "status"}
            mock_nd.match_properties.return_value = {
                "task_name": "Task", "task_status": "Status",
                "task_priority": None, "task_due_date": None,
                "task_jira_key": None, "meeting_title": "Meeting name",
                "meeting_category": None, "meeting_date": None,
                "meeting_url": None, "meeting_summary": None,
            }
            result = runner.invoke(ctx.app, ["configure", "--notion"])

    assert "→" in result.output
    assert "task_name" in result.output
    assert "Schema saved" in result.output
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
uv run pytest tests/test_cli.py::test_configure_notion_prints_arrow_format -v
```

Expected: FAIL (current output uses `: ` not `→` and says "Notion schema updated:" not "Schema saved.")

- [ ] **Step 3: Update `_run_notion_discovery` output lines**

In `src/wizard/cli/main.py`, update `_run_notion_discovery`:

Replace:
```python
    typer.echo("Fetching Notion database schemas...")
```
With:
```python
    typer.echo("  Discovering schema...")
```

Replace:
```python
    typer.echo("Notion schema updated:")
    for k, v in schema.items():
        typer.echo(f"  {k}: {v}")
```
With:
```python
    for k, v in schema.items():
        typer.echo(f"    {k:<20} → {v}")
    typer.echo("  Schema saved.")
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/test_cli.py::test_configure_notion_prints_arrow_format -v
```

Expected: PASS

- [ ] **Step 5: Update the existing `test_configure_notion_runs_discovery` test**

The existing test asserts `result.exit_code == 0` and that `fetch_db_properties` and `match_properties` were called — it does not assert on specific output strings, so it should still pass. Confirm:

```bash
uv run pytest tests/test_cli.py::test_configure_notion_runs_discovery -v
```

Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli.py
git commit -m "feat: improve notion discovery output — arrow format and Schema saved footer"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Ask which integrations (Notion/Jira/Both/Neither) — Task 1
- ✅ Collect only chosen credentials — Tasks 2, 3
- ✅ Run Notion schema discovery immediately after collecting credentials — Task 2
- ✅ Skip already-configured integrations + print hint — Task 4
- ✅ Final summary block — Task 4
- ✅ `configure --jira` — Task 5
- ✅ Verbose output with arrow format — Task 6
- ✅ All steps print meaningful output — covered across Tasks 2–6

**Type/naming consistency:**
- `_notion_is_configured` / `_jira_is_configured` used consistently in Task 4
- `_configure_notion` / `_configure_jira` used consistently in Tasks 2, 3, 5
- `configure_notion` / `configure_jira` local booleans in `setup()` — consistent throughout
- `notion_status` / `jira_status` strings in summary block — consistent

**No placeholders found.**
