"""Należności: salda dłużników, kontrola zmian klasyfikacji i podpowiedzi spłat."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from finbro.domain.enums import TxType
from finbro.domain.history import CounterpartyKey
from finbro.domain.money import Money
from finbro.domain.receivables import (
    ReceivableError,
    ReceivableEvent,
    balance,
    check_forgiveness,
    check_repayment,
    events_for,
    forgiveness_transaction,
    oldest_unpaid_loan_date,
)
from finbro.domain.reference import Debtor
from finbro.domain.text import fold
from finbro.domain.transactions import Classification, Direction, Transaction
from finbro.services.uow import UnitOfWork


@dataclass(frozen=True)
class DebtorBalance:
    debtor: Debtor
    balance: Money
    oldest_unpaid: date | None
    events: list[ReceivableEvent]


def name_matches(debtor: Debtor, counterparty: str | None) -> bool:
    """Wszystkie słowa nazwy dłużnika (lub aliasu) występują w nazwie kontrahenta."""
    words = set(fold(counterparty).replace("-", " ").split())
    if not words:
        return False
    return any(set(fold(name).replace("-", " ").split()) <= words for name in debtor.names if name.strip())


class ReceivablesService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def _related(self) -> list[Transaction]:
        return self.uow.transactions.debtor_related()

    def balances(self, include_zero: bool = False) -> list[DebtorBalance]:
        related = self._related()
        result = []
        for debtor in self.uow.reference.debtors():
            events = events_for(related, debtor.id)
            b = balance(events)
            if include_zero or not b.is_zero:
                result.append(DebtorBalance(debtor, b, oldest_unpaid_loan_date(events), events))
        return result

    def of(self, debtor_id: int) -> DebtorBalance:
        debtor = self.uow.reference.debtor(debtor_id)
        events = events_for(self._related(), debtor_id)
        return DebtorBalance(debtor, balance(events), oldest_unpaid_loan_date(events), events)

    def total(self, balances: list[DebtorBalance] | None = None) -> Money:
        items = balances if balances is not None else self.balances()
        return sum((b.balance for b in items), Money.zero())

    def forgive(self, debtor_id: int, amount: Money, day: date, category_id: int) -> Transaction:
        """Darowanie całości lub części salda: zmniejsza saldo i jest wydatkiem w wybranej kategorii."""
        # Import lokalny: ClassificationService sam korzysta z ReceivablesService.
        from finbro.services.classification import ClassificationService

        current = self.of(debtor_id)
        check_forgiveness(current.balance, amount, current.debtor.name)
        data, classification = forgiveness_transaction(debtor_id, amount, day, category_id, current.debtor.name)
        try:
            tx = self.uow.transactions.add(data)
            tx = ClassificationService(self.uow).confirm(tx, classification)
        except Exception:
            self.uow.rollback()
            raise
        self.uow.commit()
        return tx

    def history(self, debtor_id: int) -> list[Transaction]:
        return [t for t in self._related() if t.classification.debtor_id == debtor_id]

    def check_change(self, tx: Transaction, new: Classification) -> None:
        """Nowa klasyfikacja nie może dać ujemnego salda żadnego z dotkniętych dłużników."""
        old = tx.classification
        affected = {d for d in (old.debtor_id if old.confirmed else None, new.debtor_id) if d is not None}
        if not affected:
            return
        others = [t for t in self._related() if t.id != tx.id]
        changed = replace(tx, classification=replace(new, confirmed=True))
        for debtor_id in affected:
            debtor = self.uow.reference.debtor(debtor_id)
            if new.type is TxType.SPLATA and new.debtor_id == debtor_id:
                check_repayment(balance(events_for(others, debtor_id)), abs(tx.amount), debtor.name)
            if balance(events_for([*others, changed], debtor_id)).is_negative:
                raise ReceivableError(
                    f"Zmiana spowodowałaby ujemne saldo należności: {debtor.name}. "
                    "Najpierw popraw spłaty tej osoby."
                )

    def suggest_repayment(self, tx: Transaction, balances: list[DebtorBalance] | None = None) -> DebtorBalance | None:
        """Dłużnik z niezerowym saldem, od którego prawdopodobnie pochodzi wpływ."""
        if tx.direction is not Direction.IN or tx.classification.confirmed:
            return None
        candidates = balances if balances is not None else self.balances()
        key = CounterpartyKey.of(tx.data)
        if key.account:
            for t in self._related():
                if CounterpartyKey.of(t.data).account == key.account:
                    match = next((b for b in candidates if b.debtor.id == t.classification.debtor_id), None)
                    if match is not None:
                        return match
        return next((b for b in candidates if name_matches(b.debtor, tx.data.counterparty_name)), None)
