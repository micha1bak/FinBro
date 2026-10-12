from datetime import date

import pytest

from finbro.domain.enums import TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.receivables import (
    EventKind,
    ReceivableError,
    ReceivableEvent,
    balance,
    check_forgiveness,
    check_repayment,
    events_for,
    forgiveness_transaction,
    oldest_unpaid_loan_date,
)
from finbro.domain.transactions import Classification, Transaction, TransactionData

KUBA, MARTYNA = 1, 2


def ev(kind: EventKind, amount: str, day: date = date(2026, 10, 6)) -> ReceivableEvent:
    return ReceivableEvent(kind=kind, day=day, amount=Money.parse(amount))


def tx(tx_id: int, amount: str, tx_type: TxType, debtor: int, source=TxSource.IMPORT, confirmed=True, day=date(2026, 10, 6)):
    return Transaction(
        id=tx_id,
        data=TransactionData(source=source, transaction_date=day, amount=Money.parse(amount)),
        classification=Classification(type=tx_type, debtor_id=debtor, confirmed=confirmed),
    )


def test_balance_after_loan_and_repayment():
    assert balance([ev(EventKind.LOAN, "200"), ev(EventKind.REPAYMENT, "50")]) == Money.parse("150.00")


def test_partial_repayment():
    events = [ev(EventKind.LOAN, "1290"), ev(EventKind.REPAYMENT, "500")]
    assert balance(events) == Money.parse("790.00")


def test_repayment_greater_than_balance_is_rejected_with_balance():
    with pytest.raises(ReceivableError, match="Kuba ma saldo 150,00"):
        check_repayment(Money.parse("150.00"), Money.parse("300.00"), "Kuba")
    check_repayment(Money.parse("150.00"), Money.parse("150.00"), "Kuba")


def test_forgiveness_reduces_balance_and_is_an_expense():
    events = [ev(EventKind.LOAN, "200"), ev(EventKind.REPAYMENT, "50"), ev(EventKind.FORGIVENESS, "150")]
    assert balance(events) == Money.zero()
    data, classification = forgiveness_transaction(KUBA, Money.parse("150.00"), date(2026, 11, 15), 10, "Kuba")
    assert data.amount == Money.parse("-150.00")
    assert data.transaction_date == date(2026, 11, 15)
    assert data.account_id is None
    assert data.source is TxSource.FORGIVENESS
    assert (classification.type, classification.category_id, classification.debtor_id) == (TxType.WYDATEK, 10, KUBA)


def test_forgiveness_limits():
    with pytest.raises(ReceivableError, match="saldo 150,00"):
        check_forgiveness(Money.parse("150.00"), Money.parse("150.01"), "Kuba")
    with pytest.raises(ReceivableError):
        check_forgiveness(Money.parse("150.00"), Money.zero(), "Kuba")


def test_oldest_unpaid_loan_fifo():
    events = [
        ev(EventKind.LOAN, "100", date(2026, 10, 1)),
        ev(EventKind.LOAN, "200", date(2026, 10, 5)),
        ev(EventKind.REPAYMENT, "120", date(2026, 10, 9)),
    ]
    assert oldest_unpaid_loan_date(events) == date(2026, 10, 5)
    assert oldest_unpaid_loan_date(events[:2] + [ev(EventKind.REPAYMENT, "99.99")]) == date(2026, 10, 1)
    assert oldest_unpaid_loan_date(events + [ev(EventKind.FORGIVENESS, "180")]) is None
    assert oldest_unpaid_loan_date([]) is None


def test_events_from_transactions():
    txs = [
        tx(1, "-645.00", TxType.POZYCZKA, MARTYNA),
        tx(2, "+500.00", TxType.SPLATA, MARTYNA, day=date(2026, 10, 11)),
        tx(3, "-200.00", TxType.POZYCZKA, KUBA),
        tx(4, "-100.00", TxType.POZYCZKA, MARTYNA, confirmed=False),
        tx(5, "-50.00", TxType.WYDATEK, MARTYNA, source=TxSource.FORGIVENESS, day=date(2026, 11, 15)),
        tx(6, "-30.00", TxType.WYDATEK, MARTYNA),  # zwykły wydatek nie zmienia salda
    ]
    events = events_for(txs, MARTYNA)
    assert [(e.kind, e.amount, e.transaction_id) for e in events] == [
        (EventKind.LOAN, Money.parse("645.00"), 1),
        (EventKind.REPAYMENT, Money.parse("500.00"), 2),
        (EventKind.FORGIVENESS, Money.parse("50.00"), 5),
    ]
    assert balance(events) == Money.parse("95.00")
