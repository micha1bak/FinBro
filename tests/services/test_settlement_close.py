from datetime import date

import pytest

from finbro.domain.enums import SettlementStatus, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.transactions import TransactionData
from finbro.services.classification import ClassificationService, Decision
from finbro.services.importing import ImportService
from finbro.services.settlement import SettlementError, SettlementService
from finbro.services.wallet import WalletService
from tests.helpers import WEEK41, fixture_bytes

T41 = IsoWeek(2026, 41)
MONDAY = date(2026, 10, 12)


def by_amount(uow, amount: str):
    [tx] = [t for t in uow.transactions.list_between(date(2026, 1, 1), date(2026, 12, 31)) if t.amount == Money.parse(amount)]
    return tx


def test_running_week_cannot_be_closed(uow):
    with pytest.raises(SettlementError, match="jeszcze trwa"):
        SettlementService(uow).close(T41, today=date(2026, 10, 11))
    assert uow.settlements.get(T41) is None or uow.settlements.get(T41).status is SettlementStatus.OPEN


def test_week_before_start_date_cannot_be_closed(uow):
    with pytest.raises(SettlementError, match="przed datą startu"):
        SettlementService(uow).close(IsoWeek(2026, 40), today=MONDAY)


def test_all_three_warnings_and_their_resolution(uow):
    service = SettlementService(uow)
    warnings = service.warnings(T41)
    assert any("pokryty importami" in w for w in warnings)
    assert any("inwentaryzacji" in w for w in warnings)

    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    warnings = service.warnings(T41)
    assert not any("pokryty importami" in w for w in warnings)
    # Niezatwierdzone wpływy z T41: kancelaria, refundacja, studio, Martyna.
    [pending] = [w for w in warnings if "niezatwierdzone wpływy" in w]
    assert "4 na 5932,95" in pending.replace(" ", " ")

    classify = ClassificationService(uow)
    classify.decide(by_amount(uow, "4250.00").id, Decision(type=TxType.DOCHOD))
    classify.decide(by_amount(uow, "705.87").id, Decision(type=TxType.DOCHOD))
    [pending] = [w for w in service.warnings(T41) if "niezatwierdzone wpływy" in w]
    assert "2 na" in pending
    classify.decide(by_amount(uow, "477.08").id, Decision(type=TxType.TRANSFER))
    classify.decide(by_amount(uow, "500.00").id, Decision(type=TxType.DOCHOD))

    WalletService(uow).inventory(T41.end, Money.zero())
    assert service.warnings(T41) == []


def test_close_freezes_lines(uow):
    ImportService(uow).import_pko_xml(fixture_bytes(WEEK41))
    ClassificationService(uow).decide(by_amount(uow, "4250.00").id, Decision(type=TxType.DOCHOD))
    late = uow.transactions.add(
        TransactionData(source=TxSource.MANUAL, account_id=uow.reference.account("pko").id,
                        transaction_date=date(2026, 10, 9), amount=Money.parse("+1000.00"), counterparty_name="X")
    )
    service = SettlementService(uow)
    before = service.compute(T41).settlement.lines

    closed = service.close(T41, today=MONDAY)
    assert closed.settlement.status is SettlementStatus.CLOSED
    assert closed.settlement.closed_at is not None
    assert [(l.envelope_id, l.due, l.to_transfer) for l in closed.settlement.lines] == [
        (l.envelope_id, l.due, l.to_transfer) for l in before
    ]

    # Późno zatwierdzony dochód z T41 nie zmienia zamkniętego rozliczenia.
    approved = ClassificationService(uow).decide(late.id, Decision(type=TxType.DOCHOD))
    assert approved.classification.settlement_week == IsoWeek(2026, 42).start
    assert service.compute(T41).settlement.lines == closed.settlement.lines
    assert service.compute(IsoWeek(2026, 42)).correction_total == Money.parse("1000.00")

    with pytest.raises(SettlementError, match="już zamknięte"):
        service.close(T41, today=MONDAY)


def test_close_with_warnings_is_allowed(uow):
    result = SettlementService(uow).close(T41, today=MONDAY)
    assert result.settlement.status is SettlementStatus.CLOSED
    assert all(l.to_transfer == Money.zero() for l in result.settlement.lines)
