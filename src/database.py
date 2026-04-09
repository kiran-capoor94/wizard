from contextlib import contextmanager
from typing import Generator

from sqlmodel import Session, create_engine

from .config import settings


def _db_url(path: str) -> str:
    if path == ":memory:":
        return "sqlite://"
    return f"sqlite:///{path}"


engine = create_engine(
    _db_url(settings.db),
    connect_args={"check_same_thread": False},
)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
