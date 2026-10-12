"""Raporty przychodów i wydatków dla tygodni, miesięcy i lat."""

from __future__ import annotations

from dataclasses import dataclass

from finbro.domain.periods import Period, PeriodKind, periods_ending_at
from finbro.domain.reporting import (
    CategoryShare,
    CounterpartyTotal,
    Incomplete,
    PeriodTotals,
    category_breakdown,
    incomplete,
    top_counterparties,
    totals,
    trend,
)
from finbro.services.uow import UnitOfWork

TREND_LENGTH = {PeriodKind.WEEK: 12, PeriodKind.MONTH: 12, PeriodKind.YEAR: 5}


@dataclass(frozen=True)
class Report:
    period: Period
    totals: PeriodTotals
    trend: list[PeriodTotals]
    categories: list[CategoryShare]
    counterparties: list[CounterpartyTotal]
    incomplete: Incomplete


class ReportService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def report(self, period: Period) -> Report:
        periods = periods_ending_at(period, TREND_LENGTH[period.kind])
        transactions = self.uow.transactions.list_between(periods[0].start, period.end)
        return Report(
            period=period,
            totals=totals(transactions, period),
            trend=trend(transactions, periods),
            categories=category_breakdown(transactions, period),
            counterparties=top_counterparties(transactions, period),
            incomplete=incomplete(transactions, period),
        )
