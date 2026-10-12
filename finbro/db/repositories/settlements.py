"""Repozytorium rozliczeń tygodniowych."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from finbro.db import models
from finbro.domain.enums import SettlementStatus
from finbro.domain.money import Money
from finbro.domain.periods import IsoWeek
from finbro.domain.settlement import Settlement, SettlementLine


def line_to_domain(row: models.SettlementLine) -> SettlementLine:
    return SettlementLine(
        id=row.id,
        envelope_id=row.envelope_id,
        due=Money(row.due),
        corrections=Money(row.corrections),
        carryover=Money(row.carryover),
    )


def settlement_to_domain(row: models.Settlement) -> Settlement:
    return Settlement(
        id=row.id,
        week=IsoWeek.of(row.week_start),
        status=row.status,
        closed_at=row.closed_at,
        lines=tuple(line_to_domain(line) for line in row.lines),
    )


class SettlementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _row(self, week: IsoWeek) -> models.Settlement | None:
        return self.session.scalar(
            select(models.Settlement)
            .where(models.Settlement.week_start == week.start)
            .options(selectinload(models.Settlement.lines))
        )

    def get(self, week: IsoWeek) -> Settlement | None:
        row = self._row(week)
        return settlement_to_domain(row) if row is not None else None

    def save_closed(self, settlement: Settlement) -> Settlement:
        """Zapisuje zamknięte rozliczenie z liniami. Linie raz zapisane są niezmienne."""
        row = self._row(settlement.week)
        if row is None:
            row = models.Settlement(week_start=settlement.week.start)
            self.session.add(row)
        elif row.lines:
            raise ValueError(f"Rozliczenie {settlement.week.label} ma już zapisane linie")
        row.status = settlement.status
        row.closed_at = settlement.closed_at
        row.lines = [
            models.SettlementLine(
                envelope_id=line.envelope_id,
                due=line.due.grosze,
                corrections=line.corrections.grosze,
                carryover=line.carryover.grosze,
                to_transfer=line.to_transfer.grosze,
            )
            for line in settlement.lines
        ]
        self.session.flush()
        self.session.refresh(row)
        return settlement_to_domain(row)

    def set_status(self, week: IsoWeek, status: SettlementStatus) -> None:
        row = self._row(week)
        if row is None:
            raise LookupError(f"Brak rozliczenia {week.label}")
        row.status = status
        self.session.flush()

    def list_all(self) -> list[Settlement]:
        rows = self.session.scalars(
            select(models.Settlement).options(selectinload(models.Settlement.lines)).order_by(models.Settlement.week_start)
        )
        return [settlement_to_domain(r) for r in rows]
