import json
import pytest
from sqlmodel import Session, SQLModel


@pytest.fixture(autouse=True)
def db_session(monkeypatch, tmp_path):
    import sys

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"db": ":memory:"}))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    for mod in ["src.config", "src.database", "src.models"]:
        monkeypatch.delitem(sys.modules, mod, raising=False)

    SQLModel.metadata.clear()
    SQLModel._sa_registry.dispose(cascade=True)

    from src.database import engine
    import src.models

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
