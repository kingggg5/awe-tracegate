from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config
database_url = os.environ.get("AWE_HARNESS_DATABASE_URL")
schema = os.environ.get("AWE_HARNESS_SCHEMA")
if not database_url or not schema:
    raise RuntimeError("AWE_HARNESS_DATABASE_URL and AWE_HARNESS_SCHEMA are required")
sqlalchemy_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", sqlalchemy_url)


def run_migrations_offline() -> None:
    context.configure(
        url=sqlalchemy_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    with connectable.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        context.configure(connection=connection, version_table_schema=schema)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
