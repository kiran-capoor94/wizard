import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, create_engine

from .config import settings

logger = logging.getLogger(__name__)


def _db_url(path: str) -> str:
    if path == ":memory:":
        return "sqlite://"
    return f"sqlite:///{path}"


engine = create_engine(
    _db_url(settings.db),
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


logger.info("Database engine created: %s", settings.db)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
