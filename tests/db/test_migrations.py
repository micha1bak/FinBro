"""Migracje na świeżej, tymczasowej bazie PostgreSQL."""

import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from finbro.db import migrate
from finbro.db.models import Base


@pytest.fixture
def scratch_database_url(db_engine, test_database_url):
    """Tworzy pustą bazę na czas testu i usuwa ją po nim."""
    name = f"finbro_mig_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(test_database_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(test_database_url).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin_engine.dispose()


def table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_check_and_downgrade(scratch_database_url):
    migrate.upgrade(scratch_database_url)
    assert set(Base.metadata.tables) <= table_names(scratch_database_url)

    # Brak rozbieżności między modelami a migracjami.
    migrate.check(scratch_database_url)

    migrate.downgrade(scratch_database_url)
    assert table_names(scratch_database_url) <= {"alembic_version"}

    # Migracje da się ponownie zastosować po wycofaniu.
    migrate.upgrade(scratch_database_url)
    assert set(Base.metadata.tables) <= table_names(scratch_database_url)
