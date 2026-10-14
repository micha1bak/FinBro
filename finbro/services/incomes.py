"""Dochody i plan podziału: zapis, walidacja, podział i podsumowanie miesiąca."""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from finbro.db.models import AllocationPlan, Income, IncomeShare
from finbro.domain.allocation import Plan, PlanError, Split, plan_for, split, total
from finbro.domain.envelopes import Envelope
from finbro.domain.money import Money

MAX_SOURCE_LENGTH = 200


class IncomeError(ValueError):
    """Niepoprawny dochód albo niedozwolona operacja (komunikat dla użytkownika)."""


@dataclass(frozen=True)
class IncomeView:
    id: int
    date: date
    source: str
    amount: Money
    split: Split
    settlement_id: int | None

    @property
    def settled(self) -> bool:
        return self.settlement_id is not None


@dataclass(frozen=True)
class MonthSummary:
    year: int
    month: int
    incomes: list[IncomeView]
    total: Money
    totals: Split


def plan_from_row(row: AllocationPlan) -> Plan:
    return Plan(
        row.effective_from,
        {Envelope.PKO: row.pko, Envelope.WAKACJE: row.wakacje, Envelope.XTB: row.xtb, Envelope.OBLIGACJE: row.obligacje},
    )


class IncomeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- plan podziału ---

    def plans(self) -> list[Plan]:
        rows = self.session.scalars(select(AllocationPlan).order_by(AllocationPlan.effective_from.desc()))
        return [plan_from_row(r) for r in rows]

    def add_plan(self, effective_from: date, shares: Mapping[Envelope, int]) -> Plan:
        try:
            plan = Plan(effective_from, dict(shares))
        except PlanError as exc:
            raise IncomeError(str(exc)) from exc
        exists = self.session.scalar(select(AllocationPlan.id).where(AllocationPlan.effective_from == effective_from))
        if exists is not None:
            raise IncomeError(f"Plan od {effective_from.isoformat()} już istnieje.")
        self.session.add(
            AllocationPlan(
                effective_from=effective_from,
                pko=plan.shares[Envelope.PKO],
                wakacje=plan.shares[Envelope.WAKACJE],
                xtb=plan.shares[Envelope.XTB],
                obligacje=plan.shares[Envelope.OBLIGACJE],
            )
        )
        self.session.commit()
        return plan

    # --- dochody ---

    def add(self, day: date, source: str, amount: Money) -> IncomeView:
        source, amount = self._validated(source, amount)
        income = Income(date=day, source=source, amount=amount.grosze)
        self.session.add(income)
        self.session.commit()
        return self.get(income.id)

    def update(self, income_id: int, day: date, source: str, amount: Money) -> IncomeView:
        income = self._unsettled(income_id, "zmienić")
        source, amount = self._validated(source, amount)
        income.date, income.source, income.amount = day, source, amount.grosze
        self.session.commit()
        return self.get(income_id)

    def delete(self, income_id: int) -> None:
        self.session.delete(self._unsettled(income_id, "usunąć"))
        self.session.commit()

    def get(self, income_id: int) -> IncomeView:
        income = self.session.get(Income, income_id)
        if income is None:
            raise IncomeError("Nie ma takiego dochodu.")
        return self.views([income])[0]

    def month(self, year: int, month: int) -> MonthSummary:
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        rows = self.session.scalars(
            select(Income).where(Income.date.between(first, last)).order_by(Income.date.desc(), Income.id.desc())
        ).all()
        views = self.views(rows)
        return MonthSummary(
            year=year,
            month=month,
            incomes=views,
            total=sum((v.amount for v in views), Money.zero()),
            totals=total(v.split for v in views),
        )

    def unsettled(self) -> list[IncomeView]:
        rows = self.session.scalars(
            select(Income).where(Income.settlement_id.is_(None)).order_by(Income.date, Income.id)
        ).all()
        return self.views(rows)

    # --- pomocnicze ---

    def _validated(self, source: str, amount: Money) -> tuple[str, Money]:
        source = " ".join(source.split())
        if not source:
            raise IncomeError("Podaj źródło dochodu.")
        if len(source) > MAX_SOURCE_LENGTH:
            raise IncomeError(f"Źródło może mieć najwyżej {MAX_SOURCE_LENGTH} znaków.")
        if not amount.is_positive:
            raise IncomeError("Kwota dochodu musi być większa od zera.")
        return source, amount

    def _unsettled(self, income_id: int, action: str) -> Income:
        income = self.session.get(Income, income_id)
        if income is None:
            raise IncomeError("Nie ma takiego dochodu.")
        if income.settlement_id is not None:
            raise IncomeError(f"Dochód jest rozliczony. Aby go {action}, najpierw cofnij rozliczenie.")
        return income

    def views(self, rows: Sequence[Income]) -> list[IncomeView]:
        """Widoki dochodów: podział z planu dla nierozliczonych, zamrożony dla rozliczonych."""
        plans = self.plans()
        frozen: dict[int, Split] = defaultdict(dict)
        settled_ids = [r.id for r in rows if r.settlement_id is not None]
        if settled_ids:
            for share in self.session.scalars(select(IncomeShare).where(IncomeShare.income_id.in_(settled_ids))):
                frozen[share.income_id][Envelope(share.envelope)] = Money(share.amount)
        views = []
        for r in rows:
            amount = Money(r.amount)
            parts = (
                {e: frozen[r.id].get(e, Money.zero()) for e in Envelope}
                if r.settlement_id is not None
                else split(amount, plan_for(plans, r.date))
            )
            views.append(IncomeView(r.id, r.date, r.source, amount, parts, r.settlement_id))
        return views
