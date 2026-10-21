"""Skrypt zmyślonych danych: wypełnia bazę spójnie przez serwisy i odmawia pracy poza bazą _dev."""

import random
from datetime import date

import pytest

from finbro import dev_seed
from finbro.domain.networth import Account
from finbro.services.incomes import IncomeService
from finbro.services.networth import NetWorthService
from finbro.services.settings import SettingsService
from finbro.services.settlements import SettlementService

TODAY = date(2026, 10, 21)


def test_seed_fills_every_view(db_session):
    summary = dev_seed.seed(db_session, TODAY, months=12, rng=random.Random(1))

    history = SettlementService(db_session).history()
    unsettled = IncomeService(db_session).unsettled()
    assert summary.settlements == len(history) == 11  # 12. dnia każdego miesiąca od pierwszego do poprzedniego
    assert unsettled and all(i.date > history[0].date for i in unsettled)
    assert summary.incomes > summary.unsettled
    assert len(IncomeService(db_session).plans()) == 2
    assert set(SettingsService(db_session).accounts()) == set(dev_seed.ACCOUNTS)
    overview = NetWorthService(db_session).overview(TODAY)
    assert all(overview.current.balances[a] is not None for a in Account)


def test_seed_replaces_previous_data(db_session):
    first = dev_seed.seed(db_session, TODAY, rng=random.Random(1))
    again = dev_seed.seed(db_session, TODAY, rng=random.Random(1))

    assert again == first


@pytest.mark.parametrize("database", ["finbro", "finbro_test"])
def test_main_refuses_non_dev_database(monkeypatch, capsys, database):
    monkeypatch.setenv("DATABASE_URL", f"postgresql+psycopg://finbro:x@127.0.0.1:1/{database}")

    assert dev_seed.main([]) == 1
    assert "Odmowa" in capsys.readouterr().err
