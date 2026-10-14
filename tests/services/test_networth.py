from datetime import date

import pytest

from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money
from finbro.services.incomes import IncomeService
from finbro.services.networth import NetWorthError, NetWorthService
from finbro.services.settlements import SettlementService

P, W, X, O = Envelope.PKO, Envelope.WAKACJE, Envelope.XTB, Envelope.OBLIGACJE
OCT12, OCT19 = date(2026, 10, 12), date(2026, 10, 19)


def zl(text):
    return Money.parse(text)


@pytest.fixture
def networth(db_session):
    return NetWorthService(db_session)


def settle_two_incomes(db_session, day=OCT19):
    incomes = IncomeService(db_session)
    incomes.add(date(2026, 10, 5), "Stypendium", zl("2401,30"))
    incomes.add(date(2026, 10, 14), "Zlecenie", zl("174"))
    settlements = SettlementService(db_session)
    pending = settlements.pending(day)
    return settlements.settle(pending.income_ids, pending.expected, day)


def test_empty_overview(networth):
    overview = networth.overview(OCT19)
    assert overview.is_empty and overview.timeline == [] and overview.current.total == Money.zero()


def test_settlement_increases_xtb_and_bonds_but_not_pko(db_session, networth):
    networth.record(P, OCT12, zl("3000"))
    networth.record(X, OCT12, zl("1200"))
    networth.record(O, OCT12, zl("1088,25"))
    settle_two_incomes(db_session)
    overview = networth.overview(OCT19)
    assert overview.current.balances == {P: zl("3000"), X: zl("1522"), O: zl("1410,25")}
    assert overview.current.total == zl("5932,25")
    assert overview.last_update == OCT19
    assert [s.total for s in overview.timeline] == [zl("5288,25"), zl("5932,25")]


def test_record_shows_difference_and_replaces_same_day(db_session, networth):
    networth.record(X, OCT12, zl("1200"))
    settle_two_incomes(db_session)
    view = networth.record(X, date(2026, 11, 1), zl("1560"))
    assert view.difference == zl("38")
    view = networth.record(X, date(2026, 11, 1), zl("1500"))
    assert view.difference == zl("-22")
    assert [e.entry.amount for e in networth.overview(date(2026, 11, 1)).entries] == [zl("1500"), zl("1200")]
    assert networth.record(P, OCT12, zl("3000")).difference is None


def test_undo_settlement_lowers_computed_balance(db_session, networth):
    networth.record(X, OCT12, zl("1200"))
    settlement = settle_two_incomes(db_session)
    assert networth.overview(OCT19).current.balances[X] == zl("1522")
    SettlementService(db_session).undo(settlement.id)
    assert networth.overview(OCT19).current.balances[X] == zl("1200")


@pytest.mark.parametrize("account, amount, message", [(W, zl("10"), "PKO, XTB i Obligacji"), (X, zl("-1"), "ujemne")])
def test_invalid_entry(networth, account, amount, message):
    with pytest.raises(NetWorthError, match=message):
        networth.record(account, OCT12, amount)
