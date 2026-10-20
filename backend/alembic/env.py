"""Migraciones con driver síncrono (psycopg): permite ejecutar schema.sql completo en un solo paso."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def url_sincronica() -> str:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    return url.replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(url=url_sincronica(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url_sincronica(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
