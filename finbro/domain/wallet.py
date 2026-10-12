"""Portfel gotówkowy: oczekiwany stan i inwentaryzacja."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from finbro.domain.enums import TransferKind, TxType
from finbro.domain.money import Money
from finbro.domain.transactions import Transaction


def wallet_effect(tx: Transaction, wallet_account_id: int) -> Money | None:
    """Wpływ transakcji na oczekiwany stan Portfela albo ``None``, gdy go nie dotyczy.

    - Transakcje na koncie Portfel (gotówkowe dochody, wydatki, pożyczki, spłaty,
      różnice inwentaryzacji) zmieniają stan o swoją kwotę ze znakiem.
    - Zatwierdzony transfer własny z udziałem Portfela na innym koncie działa odwrotnie:
      wypłata z bankomatu (-2300 na koncie) to +2300 w Portfelu, wpłata gotówki (+1000) to -1000.
    """
    if tx.data.account_id == wallet_account_id:
        return tx.amount
    c = tx.classification
    if c.confirmed and c.type is TxType.TRANSFER and c.transfer_kind is TransferKind.WALLET:
        return -tx.amount
    return None


@dataclass(frozen=True)
class WalletEntry:
    transaction: Transaction
    effect: Money


def wallet_entries(transactions: Iterable[Transaction], wallet_account_id: int) -> list[WalletEntry]:
    entries = []
    for tx in transactions:
        effect = wallet_effect(tx, wallet_account_id)
        if effect is not None:
            entries.append(WalletEntry(tx, effect))
    return sorted(entries, key=lambda e: (e.transaction.transaction_date, e.transaction.id))


def expected_balance(
    opening: Money,
    opening_date: date | None,
    transactions: Iterable[Transaction],
    wallet_account_id: int,
    at: date,
) -> Money:
    """Stan oczekiwany na koniec dnia ``at``: stan początkowy plus zmiany od dnia startu."""
    total = opening if opening_date is None or opening_date <= at else Money.zero()
    for entry in wallet_entries(transactions, wallet_account_id):
        day = entry.transaction.transaction_date
        if day > at or (opening_date is not None and day < opening_date):
            continue
        total += entry.effect
    return total


@dataclass(frozen=True)
class Inventory:
    id: int
    inventory_date: date
    actual: Money
    expected: Money
    transaction_id: int | None

    @property
    def difference(self) -> Money:
        return self.actual - self.expected
