"""Podpowiedź z historii kontrahenta (D9, krok 2)."""

from __future__ import annotations

from dataclasses import dataclass

from finbro.domain.accounts import normalize_account
from finbro.domain.enums import ProposalSource
from finbro.domain.text import fold
from finbro.domain.transactions import Classification, Direction, Transaction, TransactionData


@dataclass(frozen=True)
class CounterpartyKey:
    """Klucze wyszukiwania podobnych transakcji: rachunek kontrahenta, a gdy go brak, nazwa."""

    direction: Direction
    account: str | None
    name: str | None

    @classmethod
    def of(cls, tx: TransactionData) -> CounterpartyKey:
        account = normalize_account(tx.counterparty_account)
        if account[:2].isalpha():
            account = account[2:]
        name = fold(tx.counterparty_name or tx.merchant)
        return cls(direction=tx.direction, account=account or None, name=name or None)

    @property
    def usable(self) -> bool:
        return bool(self.account or self.name)


def history_proposal(previous: Transaction) -> Classification:
    """Propozycja typu i kategorii skopiowana z ostatniej zatwierdzonej transakcji kontrahenta."""
    c = previous.classification
    who = previous.counterparty or "tego kontrahenta"
    return Classification(
        type=c.type,
        category_id=c.category_id,
        debtor_id=c.debtor_id,
        transfer_kind=c.transfer_kind,
        source=ProposalSource.HISTORY,
        reason=f"Jak poprzednia transakcja: {who} z {previous.transaction_date.isoformat()}",
    )
