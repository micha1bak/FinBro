"""Rozliczenia tygodniowe: obiekty domenowe."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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
