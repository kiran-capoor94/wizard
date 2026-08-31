from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import wizard.models  # noqa: F401, E402 — registers Task, Meeting, MeetingTasks with SQLModel.metadata
from wizard.database import engine, migration_mode  # noqa: E402

config.set_main_option("sqlalchemy.url", str(engine.url))

target_metadata = SQLModel.metadata

_FTS_SUFFIXES = ("_fts", "_fts_data", "_fts_idx", "_fts_docsize", "_fts_config")

# Virtual tables (sqlite-vec) and unmanaged legacy tables — excluded from autogenerate
_EXCLUDE_TABLES = frozenset({
    "code_chunk",
    "vec_note_embeddings",
    "vec_note_embeddings_chunks",
    "vec_note_embeddings_info",
    "vec_note_embeddings_rowids",
    "vec_note_embeddings_vector_chunks00",
})


def _include_object(obj, name, type_, reflected, _compare_to):  # noqa: ARG001
    if type_ == "table":
        return not (name.endswith(_FTS_SUFFIXES) or name in _EXCLUDE_TABLES)
    return True


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
    with migration_mode(), engine.connect() as connection:
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
