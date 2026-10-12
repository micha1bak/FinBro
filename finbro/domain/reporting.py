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
from finbro.domain.text import fold
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


@dataclass(frozen=True)
class CategoryShare:
    category_id: int | None
    amount: Money
    share_bp: int  # udział w punktach bazowych (100% = 10000)

    @property
    def percent(self) -> str:
        whole, frac = divmod(self.share_bp, 100)
        return (f"{whole},{frac:02d}".rstrip("0").rstrip(",")) + "%"


@dataclass(frozen=True)
class CounterpartyTotal:
    name: str
    amount: Money
    count: int


@dataclass(frozen=True)
class Incomplete:
    """Pozycje "do klasyfikacji" i niezatwierdzone wpływy w okresie (niewliczone do sum)."""

    count: int
    total: Money


def share_bp(part: Money, total: Money) -> int:
    if not total.is_positive:
        return 0
    return round(part.grosze * 10_000 / total.grosze)


def category_breakdown(transactions: Iterable[Transaction], period: Period) -> list[CategoryShare]:
    by_category = expenses_by_category(in_period(transactions, period))
    total = sum(by_category.values(), Money.zero())
    shares = [CategoryShare(cat, amount, share_bp(amount, total)) for cat, amount in by_category.items() if not amount.is_zero]
    return sorted(shares, key=lambda s: (-s.amount.grosze, s.category_id or 0))


def top_counterparties(transactions: Iterable[Transaction], period: Period, limit: int = 10) -> list[CounterpartyTotal]:
    """Sprzedawcy i kontrahenci z największą sumą wydatków (nazwy porównywane po normalizacji)."""
    totals_by_name: dict[str, tuple[str, Money, int]] = {}
    for t in in_period(transactions, period):
        contribution = expense_of(t)
        name = t.counterparty or t.data.note
        if contribution.is_zero or not name:
            continue
        key = fold(name)
        label, amount, n = totals_by_name.get(key, (name, Money.zero(), 0))
        totals_by_name[key] = (label, amount + contribution, n + 1)
    ranking = [CounterpartyTotal(label, amount, n) for label, amount, n in totals_by_name.values() if amount.is_positive]
    return sorted(ranking, key=lambda c: (-c.amount.grosze, c.name))[:limit]


def incomplete(transactions: Iterable[Transaction], period: Period) -> Incomplete:
    items = [t for t in in_period(transactions, period) if t.classification.type is None or not t.classification.confirmed]
    return Incomplete(count=len(items), total=sum((abs(t.amount) for t in items), Money.zero()))
