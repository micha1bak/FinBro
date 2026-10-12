"""Izolacja testów bazodanowych i komunikat przy braku bazy."""

import pytest
from sqlalchemy import func, select

from finbro.db.models import Debtor
from finbro.db.session import make_engine
from tests.conftest import require_database

UNREACHABLE_URL = "postgresql+psycopg://finbro:x@127.0.0.1:1/finbro_test"


def _write_same_row(db_session):
    db_session.add(Debtor(name="Testowy Dłużnik Izolacji"))
    db_session.commit()  # zatwierdza tylko savepoint wewnątrz transakcji testu
    count = db_session.scalar(select(func.count()).select_from(Debtor).where(Debtor.name == "Testowy Dłużnik Izolacji"))
    assert count == 1


# Dwa testy zapisują ten sam unikalny wiersz: oba przechodzą tylko wtedy,
# gdy zmiany pierwszego są wycofane przed drugim (w dowolnej kolejności).
def test_isolation_first(db_session):
    _write_same_row(db_session)


def test_isolation_second(db_session):
    _write_same_row(db_session)


def test_unreachable_database_gives_instruction():
    engine = make_engine(UNREACHABLE_URL)
    try:
        with pytest.raises(pytest.fail.Exception, match="docker compose up -d db"):
            require_database(engine)
    finally:
        engine.dispose()
