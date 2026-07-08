import importlib.resources
import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlmodel import Session, create_engine

from .config import settings

logger = logging.getLogger(__name__)


def _db_url(path: str) -> str:
    if path == ":memory:":
        return "sqlite://"
    return f"sqlite:///{path}"


engine = create_engine(
    _db_url(settings.db),
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    # SQLite disables FK enforcement per-connection by default — without this,
    # ondelete="CASCADE" on TaskState.task_id (models.py) is a no-op and deleting
    # a Task orphans its TaskState row instead of cascading.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@event.listens_for(engine, "connect")
def _load_sqlite_vec(dbapi_conn, _connection_record) -> None:
    try:
        import sqlite_vec
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
        dbapi_conn.enable_load_extension(False)
    except Exception as e:
        logger.warning("sqlite-vec extension not loaded: %s", e)


logger.info("Database engine created: %s", settings.db)


def create_vec_tables() -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_note_embeddings "
                "USING vec0(note_id INTEGER PRIMARY KEY, "
                "embedding float[384] distance_metric=cosine)"
            ))
            conn.commit()
    except Exception as e:
        logger.warning("vec_note_embeddings table not created: %s", e)


create_vec_tables()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def run_migrations() -> None:
    """Run alembic upgrade head using the bundled migrations.

    Works whether wizard is an editable install (dev) or a uv tool install
    (production) — importlib.resources resolves the correct path in both cases.
    """
    from alembic import command  # noqa: I001
    from alembic.config import Config

    alembic_dir = str(importlib.resources.files("wizard").joinpath("alembic"))
    cfg = Config()
    cfg.set_main_option("script_location", alembic_dir)
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")
