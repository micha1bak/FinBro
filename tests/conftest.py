"""Wspólne fixture'y testów FinBro.

Testy domeny nie potrzebują bazy. Testy integracyjne działają na prawdziwym
PostgreSQL w bazie ``finbro_test``: schemat powstaje migracjami raz na sesję,
a każdy test działa w transakcji wycofywanej na końcu (D11).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text
from sqlalchemy.orm import Session, sessionmaker

from finbro.config import Settings, load_dotenv
from finbro.db import migrate
from finbro.db.session import make_engine, ping
from finbro.services.uow import UnitOfWork
from finbro.web.app import create_app
from tests.helpers import MAIN_ACCOUNT

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

DB_HINT = (
    "Uruchom bazę poleceniem: docker compose up -d db "
    "(a przy pierwszym uruchomieniu skopiuj .env.example do .env i ustaw hasło)."
)


def require_database(engine: Engine) -> None:
    """Przerywa testy czytelnym komunikatem, gdy baza testowa jest nieosiągalna."""
    if not ping(engine):
        pytest.fail(
            f"Baza testowa jest nieosiągalna ({engine.url.render_as_string(hide_password=True)}). {DB_HINT}",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.fail(f"Brak zmiennej TEST_DATABASE_URL. {DB_HINT}", pytrace=False)
    return url


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[Engine]:
    engine = make_engine(test_database_url)
    require_database(engine)
    # Czysty schemat w każdej sesji testów, tworzony migracjami (testuje je przy okazji).
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    migrate.upgrade(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    """Połączenie z otwartą transakcją, wycofywaną po teście."""
    with db_engine.connect() as conn:
        outer = conn.begin()
        try:
            yield conn
        finally:
            if outer.is_active:
                outer.rollback()


@pytest.fixture
def session_factory(db_connection: Connection) -> sessionmaker[Session]:
    """Fabryka sesji w transakcji testu: commit w kodzie zamyka tylko savepoint."""
    return sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(test_database_url: str, session_factory: sessionmaker[Session]) -> FastAPI:
    """Aplikacja korzystająca z sesji w transakcji testu."""
    return create_app(Settings(database_url=test_database_url), session_factory=session_factory)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def uow(db_session: Session) -> UnitOfWork:
    """Jednostka pracy ze skonfigurowanym kontem głównym i datą startu 2026-10-05.

    Korzysta z tej samej sesji co ``db_session``, żeby savepointy w transakcji testu
    nie przeplatały się między sesjami.
    """
    unit = UnitOfWork(db_session)
    unit.reference.update_config(main_account_number=MAIN_ACCOUNT, start_date=date(2026, 10, 5))
    unit.commit()
    return unit
