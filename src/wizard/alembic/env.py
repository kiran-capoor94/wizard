from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import wizard.models  # noqa: F401, E402 — registers Task, Meeting, MeetingTasks with SQLModel.metadata
from wizard.database import engine  # noqa: E402

config.set_main_option("sqlalchemy.url", str(engine.url))

target_metadata = SQLModel.metadata

_FTS_SUFFIXES = ("_fts", "_fts_data", "_fts_idx", "_fts_docsize", "_fts_config")


def _include_object(obj, name, type_, reflected, _compare_to):  # noqa: ARG001
    return not (type_ == "table" and name.endswith(_FTS_SUFFIXES))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
