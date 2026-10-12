"""Należności: pożyczki dla osób, spłaty (także częściowe) i darowanie długu."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from finbro.domain.enums import ProposalSource, TxSource, TxType
from finbro.domain.money import Money
from finbro.domain.transactions import Classification, Transaction, TransactionData


class ReceivableError(ValueError):
    """Operacja na należności niezgodna z saldem dłużnika."""


class EventKind(StrEnum):
    LOAN = "LOAN"
    REPAYMENT = "REPAYMENT"
    FORGIVENESS = "FORGIVENESS"

    @property
    def label(self) -> str:
        return {"LOAN": "pożyczka", "REPAYMENT": "spłata", "FORGIVENESS": "darowanie"}[self.value]


@dataclass(frozen=True)
class ReceivableEvent:
    kind: EventKind
    day: date
    amount: Money  # zawsze dodatnia
    transaction_id: int | None = None


def event_from_transaction(tx: Transaction, debtor_id: int) -> ReceivableEvent | None:
    c = tx.classification
    if not c.confirmed or c.debtor_id != debtor_id:
        return None
    if tx.data.source is TxSource.FORGIVENESS:
        kind = EventKind.FORGIVENESS
    elif c.type is TxType.POZYCZKA:
        kind = EventKind.LOAN
    elif c.type is TxType.SPLATA:
        kind = EventKind.REPAYMENT
    else:
        return None
    return ReceivableEvent(kind=kind, day=tx.transaction_date, amount=abs(tx.amount), transaction_id=tx.id)


def events_for(transactions: Iterable[Transaction], debtor_id: int) -> list[ReceivableEvent]:
    events = [e for tx in transactions if (e := event_from_transaction(tx, debtor_id)) is not None]
    return sorted(events, key=lambda e: (e.day, e.transaction_id or 0))


def balance(events: Iterable[ReceivableEvent]) -> Money:
    """Saldo = suma pożyczek minus suma spłat i darowanych kwot."""
    total = Money.zero()
    for e in events:
        total += e.amount if e.kind is EventKind.LOAN else -e.amount
    return total


def check_repayment(current_balance: Money, amount: Money, debtor_name: str) -> None:
    if amount > current_balance:
        raise ReceivableError(
            f"Spłata {amount.format()} przekracza saldo należności: {debtor_name} ma saldo {current_balance.format()}."
        )


def check_forgiveness(current_balance: Money, amount: Money, debtor_name: str) -> None:
    if not amount.is_positive:
        raise ReceivableError("Darowana kwota musi być większa od zera.")
    if amount > current_balance:
        raise ReceivableError(
            f"Nie można darować więcej niż saldo: {debtor_name} ma saldo {current_balance.format()}."
        )


def oldest_unpaid_loan_date(events: Iterable[ReceivableEvent]) -> date | None:
    """Data najstarszej niespłaconej pożyczki; spłaty i darowania rozliczają najpierw najstarsze pożyczki."""
    events = list(events)
    paid = sum((e.amount for e in events if e.kind is not EventKind.LOAN), Money.zero())
    for loan in sorted((e for e in events if e.kind is EventKind.LOAN), key=lambda e: (e.day, e.transaction_id or 0)):
        if paid >= loan.amount:
            paid -= loan.amount
            continue
        return loan.day
    return None


def forgiveness_transaction(debtor_id: int, amount: Money, day: date, category_id: int, debtor_name: str) -> tuple[TransactionData, Classification]:
    """Darowana kwota to wydatek w wybranej kategorii, datowany na dzień darowania (bez ruchu pieniędzy)."""
    data = TransactionData(
        source=TxSource.FORGIVENESS,
        account_id=None,
        transaction_date=day,
        amount=-amount,
        counterparty_name=debtor_name,
        note=f"Darowanie długu: {debtor_name}",
    )
    classification = Classification(
        type=TxType.WYDATEK, category_id=category_id, debtor_id=debtor_id, source=ProposalSource.USER
    )
    return data, classification
