import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from mailbender.store.models import Base

config = context.config
_db_url = os.environ.get("MAILBENDER_DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
