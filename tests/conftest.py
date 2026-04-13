import json

import pytest
from sqlmodel import Session, SQLModel


@pytest.fixture(autouse=True)
def db_session(monkeypatch, tmp_path):
    import sys

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    for mod in [
        "wizard.config",
        "wizard.database",
        "wizard.deps",
        "wizard.integrations",
        "wizard.agent_registration",
        "wizard.models",
        "wizard.repositories",
        "wizard.schemas",
        "wizard.services",
        "wizard.tools",
        "wizard.resources",
        "wizard.cli.main",
    ]:
        monkeypatch.delitem(sys.modules, mod, raising=False)

    SQLModel.metadata.clear()
    SQLModel._sa_registry.dispose(cascade=True)

    from wizard.database import engine
    import wizard.models  # noqa: F401 — registers models with SQLModel.metadata

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
