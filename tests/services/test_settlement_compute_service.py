from datetime import date

from finbro.domain.enums import SettlementStatus, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import Settlement
from finbro.services.classification import ClassificationService, Decision
from finbro.services.importing import ImportService
from finbro.services.settlement import SettlementService
from finbro.services.wallet import WalletService
from tests.helpers import WEEK41, fixture_bytes

T41, T42 = IsoWeek(2026, 41), IsoWeek(2026, 42)


def by_amount(uow, amount: str):
    [tx] = [t for t in uow.transactions.list_between(date(2026, 1, 1), date(2026, 12, 31)) if t.amount == Money.parse(amount)]
    return tx


def envelope(week_settlement, code):
    env = next(e for e in week_settlement.envelopes if e.code == code)
    return week_settlement.line(env)


def test_week_includes_bank_and_cash_incomes(uow):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    service = ClassificationService(uow)
    for amount in ("4250.00", "705.87"):
        service.decide(by_amount(uow, amount).id, Decision(type=TxType.DOCHOD))
    WalletService(uow).add_cash_income(date(2026, 10, 7), Money.parse("800.00"))

    result = SettlementService(uow).compute(T41)
    assert result.settlement.status is SettlementStatus.OPEN
    assert result.income_total == Money.parse("5755.87")
    assert envelope(result, "wakacje").due == Money.parse("1438.96")  # 25% w dół do grosza
    assert envelope(result, "xtb").due == Money.parse("719.48")
    assert sum((l.to_transfer for l in result.settlement.lines), Money.zero()) == Money.parse("5755.87")


def test_unconfirmed_and_non_income_inflows_are_not_split(uow):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    result = SettlementService(uow).compute(T41)
    assert result.income_total == Money.zero()
    assert all(l.to_transfer == Money.zero() for l in result.settlement.lines)


def test_corrections_appear_in_next_open_week(uow):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    uow.settlements.save_closed(Settlement(week=T41, status=SettlementStatus.CLOSED))
    uow.commit()
    ClassificationService(uow).decide(by_amount(uow, "4250.00").id, Decision(type=TxType.DOCHOD))

    t42 = SettlementService(uow).compute(T42)
    assert t42.income_total == Money.zero()
    assert t42.correction_total == Money.parse("4250.00")
    assert envelope(t42, "wakacje").corrections == Money.parse("1062.50")
    assert envelope(t42, "wakacje").due == Money.zero()
