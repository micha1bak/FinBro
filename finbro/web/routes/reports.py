"""Widok raportów: tydzień, miesiąc albo rok, z trendem, kategoriami i sprzedawcami."""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from finbro.domain.periods import PeriodKind, parse_period, period_of
from finbro.services.reports import ReportService
from finbro.services.uow import UnitOfWork
from finbro.web.deps import get_uow
from finbro.web.templating import templates

router = APIRouter()

KIND_LABELS = {PeriodKind.WEEK: "Tydzień", PeriodKind.MONTH: "Miesiąc", PeriodKind.YEAR: "Rok"}


@router.get("/reports", response_class=HTMLResponse)
def reports(request: Request, uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
    try:
        kind = PeriodKind(request.query_params.get("kind", PeriodKind.MONTH.value))
    except ValueError:
        kind = PeriodKind.MONTH
    label = request.query_params.get("period")
    try:
        period = parse_period(kind, label) if label else period_of(kind, date.today())
    except ValueError:
        period = period_of(kind, date.today())

    report = ReportService(uow).report(period)
    categories = {c.id: c.name for c in uow.reference.categories()}
    chart = {
        "labels": [p.period.label for p in report.trend],
        "income": [p.income.grosze / 100 for p in report.trend],
        "expenses": [p.expenses.grosze / 100 for p in report.trend],
    }
    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "report": report,
            "kind": kind,
            "kinds": KIND_LABELS,
            "category_names": categories,
            "chart_json": json.dumps(chart),
        },
    )
