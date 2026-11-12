from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.infrastructure.database.models import Base

config = context.config

# When called from inside the app (``schema_migration.py``) a connection is passed in. In that case
# do not override the logging setup with alembic.ini (do not break the app's structured logs).
shared_connection = config.attributes.get("connection")
if shared_connection is None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./app.db")


def _configure(**kwargs: object) -> None:
    # SQLite barely supports ALTER TABLE, so make autogenerate write batch operations.
    context.configure(target_metadata=target_metadata, render_as_batch=True, **kwargs)


def run_migrations_offline() -> None:
    _configure(url=get_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if shared_connection is not None:
        _configure(connection=shared_connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
