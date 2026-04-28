from pathlib import Path

import wizard
from wizard.config import settings


def test_wizard_paths_installed_skills():
    assert settings.paths.installed_skills == Path.home() / ".wizard" / "skills"


def test_wizard_paths_package_skills():
    assert settings.paths.package_skills == Path(wizard.__file__).resolve().parent / "skills"


def test_wizard_paths_sessions_dir():
    assert settings.paths.sessions_dir == Path.home() / ".wizard" / "sessions"
