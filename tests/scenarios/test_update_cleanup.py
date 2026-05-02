import json

import wizard.agent_registration as ar


def test_refresh_hooks_deletes_obsolete_scripts(tmp_path, monkeypatch):
    """refresh_hooks should remove files in ~/.wizard/hooks that are not in the package."""
    pkg_hooks_dir = tmp_path / "pkg_hooks"
    pkg_hooks_dir.mkdir()
    (pkg_hooks_dir / "new-hook.sh").write_text("echo new")

    wizard_hooks_dir = tmp_path / "wizard_hooks"
    wizard_hooks_dir.mkdir()
    (wizard_hooks_dir / "old-obsolete-hook.sh").write_text("echo obsolete")
    (wizard_hooks_dir / "new-hook.sh").write_text("echo old-version-of-new")

    monkeypatch.setattr(ar, "_WIZARD_HOOKS_DIR", wizard_hooks_dir)

    # Mock importlib.resources.files
    class MockFiles:
        def joinpath(self, name):
            return pkg_hooks_dir

    monkeypatch.setattr("importlib.resources.files", lambda pkg: MockFiles())

    ar.refresh_hooks()

    assert (wizard_hooks_dir / "new-hook.sh").exists()
    assert (wizard_hooks_dir / "new-hook.sh").read_text() == "echo new"
    assert not (wizard_hooks_dir / "old-obsolete-hook.sh").exists()

def test_deregister_hook_aggressive_cleanup(tmp_path, monkeypatch):
    """deregister_hook should remove ANY hook pointing to the wizard hooks dir."""
    config = tmp_path / "settings.json"
    wizard_hooks_dir = tmp_path / "wizard_hooks"
    wizard_hooks_dir.mkdir()

    monkeypatch.setattr(ar, "_WIZARD_HOOKS_DIR", wizard_hooks_dir)
    monkeypatch.setitem(ar._HOOK_CONFIGS, "gemini", (config, "hooks"))

    hooks_dir_str = str(wizard_hooks_dir)
    initial_config = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": f"bash {hooks_dir_str}/session-start.sh"}]}
            ],
            "GhostEvent": [
                {"hooks": [{"type": "command", "command": f"bash {hooks_dir_str}/ghost.sh"}]}
            ],
            "OtherApp": [
                {"hooks": [{"type": "command", "command": "echo hello"}]}
            ]
        }
    }
    config.write_text(json.dumps(initial_config))

    ar.deregister_hook("gemini")

    data = json.loads(config.read_text())
    assert "SessionStart" not in data["hooks"]
    assert "GhostEvent" not in data["hooks"]
    assert "OtherApp" in data["hooks"]
    assert data["hooks"]["OtherApp"][0]["hooks"][0]["command"] == "echo hello"

def test_uninstall_skills_removes_mirrored_skills(tmp_path, monkeypatch):
    """uninstall_skills should remove skills that exist in the source_dir."""
    agent_skills_dir = tmp_path / "agent_skills"
    agent_skills_dir.mkdir()
    (agent_skills_dir / "skill-a").mkdir()
    (agent_skills_dir / "skill-b").mkdir()
    (agent_skills_dir / "manual-skill").mkdir()

    source_dir = tmp_path / "source_skills"
    source_dir.mkdir()
    (source_dir / "skill-a").mkdir()
    (source_dir / "skill-b").mkdir()

    monkeypatch.setitem(ar._AGENT_SKILLS_DIRS, "gemini", agent_skills_dir)

    ar.uninstall_skills("gemini", source_dir)

    assert not (agent_skills_dir / "skill-a").exists()
    assert not (agent_skills_dir / "skill-b").exists()
    assert (agent_skills_dir / "manual-skill").exists()
