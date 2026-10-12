"""Rozliczenia tygodniowe: obiekty domenowe."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, datetime

from finbro.domain.enums import SettlementStatus
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek


@dataclass(frozen=True)
class SettlementLine:
    """Linia rozliczenia dla jednej koperty. Po zamknięciu kwoty są niezmienne."""

    envelope_id: int
    due: Money
    corrections: Money
    carryover: Money
    id: int | None = None

    @property
    def to_transfer(self) -> Money:
        return self.due + self.corrections + self.carryover


@dataclass(frozen=True)
class Settlement:
    week: IsoWeek
    status: SettlementStatus
    lines: tuple[SettlementLine, ...] = ()
    closed_at: datetime | None = None
    id: int | None = None

    def line_for(self, envelope_id: int) -> SettlementLine | None:
        return next((line for line in self.lines if line.envelope_id == envelope_id), None)


@dataclass(frozen=True)
class SettlementPayment:
    """Przelew ODKŁADANIE zaliczony na linię rozliczenia."""

    settlement_line_id: int
    transaction_id: int
    amount: Money
    id: int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class SettlementAdjustment:
    """Ujemna korekta po wycofaniu dochodu z zamkniętego tygodnia."""

    week: IsoWeek
    transaction_id: int
    amount: Money
    income_date: date
    id: int | None = field(default=None, compare=False)


CLOSED_STATUSES = frozenset({SettlementStatus.CLOSED, SettlementStatus.SETTLED})


def nearest_open_week(week: IsoWeek, closed: Collection[IsoWeek]) -> IsoWeek:
    """Pierwszy tydzień od ``week`` (włącznie), którego rozliczenie nie jest zamknięte."""
    while week in closed:
        week = week.next()
    return week


def is_settled_income_date(income_date: date, start_date: date | None) -> bool:
    """Dochody sprzed daty startu nie podlegają podziałowi (D7, spec "Data startu")."""
    return start_date is None or income_date >= start_date
