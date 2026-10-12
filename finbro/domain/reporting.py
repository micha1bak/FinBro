"""Raporty: definicje przychodów i wydatków oraz agregacje dla okresów.

Przychody to zatwierdzone DOCHODY. Wydatki to zatwierdzone WYDATKI (także różnice
z inwentaryzacji i darowane kwoty) pomniejszone o ZWROTY i ROZLICZENIA w tej samej kategorii.
TRANSFER, ODKŁADANIE, POŻYCZKA i SPŁATA nie są ani przychodem, ani wydatkiem.
Transakcja należy do okresu według daty transakcji.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from finbro.domain.enums import TxType
from finbro.domain.money import Money
from finbro.domain.periods import Period
from finbro.domain.transactions import Transaction

INCOME_TYPES = frozenset({TxType.DOCHOD})
EXPENSE_TYPES = frozenset({TxType.WYDATEK})
EXPENSE_REDUCING_TYPES = frozenset({TxType.ZWROT, TxType.ROZLICZENIE})


def income_of(tx: Transaction) -> Money:
    c = tx.classification
    return tx.amount if c.confirmed and c.type in INCOME_TYPES else Money.zero()


def expense_of(tx: Transaction) -> Money:
    """Wkład transakcji w wydatki: dodatni dla WYDATKU, ujemny dla ZWROTU i ROZLICZENIA."""
    c = tx.classification
    if c.confirmed and (c.type in EXPENSE_TYPES or c.type in EXPENSE_REDUCING_TYPES):
        return -tx.amount
    return Money.zero()


def expenses_by_category(transactions: Iterable[Transaction]) -> dict[int | None, Money]:
    """Wydatki netto w każdej kategorii (zwrot i rozliczenie pomniejszają swoją kategorię)."""
    result: dict[int | None, Money] = defaultdict(Money.zero)
    for t in transactions:
        contribution = expense_of(t)
        if not contribution.is_zero:
            result[t.classification.category_id] += contribution
    return dict(result)


@dataclass(frozen=True)
class PeriodTotals:
    period: Period
    income: Money
    expenses: Money

    @property
    def balance(self) -> Money:
        return self.income - self.expenses


def in_period(transactions: Iterable[Transaction], period: Period) -> list[Transaction]:
    return [t for t in transactions if period.contains(t.transaction_date)]


def totals(transactions: Iterable[Transaction], period: Period) -> PeriodTotals:
    txs = in_period(transactions, period)
    return PeriodTotals(
        period=period,
        income=sum((income_of(t) for t in txs), Money.zero()),
        expenses=sum((expense_of(t) for t in txs), Money.zero()),
    )


def trend(transactions: Iterable[Transaction], periods: list[Period]) -> list[PeriodTotals]:
    """Przychody i wydatki w kolejnych okresach (wykres trendu)."""
    txs = list(transactions)
    return [totals(txs, period) for period in periods]
