"""Środowisko migracji Alembic dla FinBro."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from finbro.config import Settings, load_dotenv

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def database_url() -> str:
    # Testy przekazują adres bazy testowej przez atrybuty konfiguracji.
    url = config.attributes.get("database_url")
    if url:
        return url
    load_dotenv()
    return Settings.from_env().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
